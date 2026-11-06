// the three steps of the lab story in one small 3D scene. the world is always 10 wide and 12.5 high, the css keeps
// the canvas at that shape. one draw call for all flowing molecules: the real structure merged into one mesh, instanced

import * as THREE from "three";

const WIDTH = 10;
const HEIGHT = 12.5;
const FOV = 26;
const ATOM_TOKENS = { H: "--atom-h", C: "--atom-c", O: "--atom-o", N: "--atom-n", S: "--atom-s", Cl: "--atom-cl", F: "--atom-f" };
const ATOM_FRACTION = { C: 0.3, N: 0.29, O: 0.29, F: 0.27, S: 0.33, Cl: 0.33 };

const COPIES = 15;
const PARTICLES = 260;
const ARRIVAL_S = 1.05; // a new molecule this often. the ratio stretches this into how long the gate takes per molecule
const FREE_GATE_S = 0.55; // a free gate is faster than the arrivals, otherwise a pile would never clear
const SPEED = 2.6;
const GATE_X = 1.1;
const LANE_Y = -2;
const HERO_Y = 3.5;
const HERO_X = 2.6;
const HERO_RADIUS = 1.9;
const COPY_RADIUS = 0.78;
const GATE_RADIUS = 1.15;
// step three is a blood vessel cut open. how full it is, is how many of the drug's molecules flow in it
const VESSEL_MAX = 20;
const NORMAL_UP = 0.2; // 4 of 20 before an interaction that raises it, so 5x is exactly full
const NORMAL_DOWN = 0.8;
const TRANSPORTER_FILL = 0.5; // no number for these, so it only shows the direction
const VESSEL_R = 2.05;
const VESSEL_LENGTH = 17;
const VESSEL_OPEN = 1.1; // how far the cut reaches round from the front, in radians
const VESSEL_SPEED = 1.4;
const CELLS = 24;

const SLOW_FRAME_MS = 26;
const CHECK_EVERY_MS = 1500;

const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const color = (name) => new THREE.Color(token(name));
const clamp = THREE.MathUtils.clamp;
const easeOut = (t) => 1 - (1 - clamp(t, 0, 1)) ** 3;

function centred(raw) {
  const atoms = raw.atoms.filter((a) => a[0] !== "H").map((a) => ({ element: a[0], at: new THREE.Vector3(a[1], a[2], a[3]) }));
  const index = new Map();
  raw.atoms.forEach((a, i) => { if (a[0] !== "H") index.set(i, index.size); });
  const bonds = raw.bonds.filter(([i, j]) => index.has(i) && index.has(j)).map(([i, j]) => [index.get(i), index.get(j)]);
  const middle = atoms.reduce((sum, a) => sum.add(a.at), new THREE.Vector3()).multiplyScalar(1 / (atoms.length || 1));
  atoms.forEach((a) => a.at.sub(middle));
  const unit = bonds.reduce((sum, [i, j]) => sum + atoms[i].at.distanceTo(atoms[j].at), 0) / (bonds.length || 1) || 1.4;
  const radius = Math.max(...atoms.map((a) => a.at.length()), 0.1) + unit * 0.3;
  return { atoms, bonds, unit, radius };
}

// a whole molecule as one geometry, size 1. colours per vertex, so it stays one draw call
function moleculeGeometry(mol, detail, chunk = 1) {
  const sphere = new THREE.SphereGeometry(1, detail, Math.max(6, Math.round(detail * 0.7)));
  const tube = new THREE.CylinderGeometry(1, 1, 1, Math.max(5, Math.round(detail / 2)));
  const positions = [];
  const normals = [];
  const colors = [];
  const indices = [];
  const white = color("--strip-main");
  const add = (geometry, matrix, tint) => {
    const start = positions.length / 3;
    const p = geometry.attributes.position;
    const n = geometry.attributes.normal;
    const normalMatrix = new THREE.Matrix3().getNormalMatrix(matrix);
    const v = new THREE.Vector3();
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i).applyMatrix4(matrix);
      positions.push(v.x, v.y, v.z);
      v.fromBufferAttribute(n, i).applyMatrix3(normalMatrix).normalize();
      normals.push(v.x, v.y, v.z);
      colors.push(tint.r, tint.g, tint.b);
    }
    for (let i = 0; i < geometry.index.count; i++) indices.push(start + geometry.index.getX(i));
  };
  const scale = 1 / mol.radius;
  const m = new THREE.Matrix4();
  for (const a of mol.atoms) {
    const r = (ATOM_FRACTION[a.element] ?? 0.33) * mol.unit * scale * chunk;
    m.makeScale(r, r, r).setPosition(a.at.clone().multiplyScalar(scale));
    add(sphere, m, color(ATOM_TOKENS[a.element] ?? "--atom-cl").lerp(white, 0.25));
  }
  const bond = color("--bond");
  const up = new THREE.Vector3(0, 1, 0);
  for (const [i, j] of mol.bonds) {
    const from = mol.atoms[i].at.clone().multiplyScalar(scale);
    const to = mol.atoms[j].at.clone().multiplyScalar(scale);
    const direction = to.clone().sub(from);
    const r = 0.055 * mol.unit * scale * chunk;
    m.compose(from.clone().add(to).multiplyScalar(0.5), new THREE.Quaternion().setFromUnitVectors(up, direction.clone().normalize()),
      new THREE.Vector3(r, direction.length(), r));
    add(tube, m, bond);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.setIndex(indices);
  return geometry;
}

// each atom keeps a little light of its own colour, on a dark page glass only shows what it reflects otherwise
function withBody(material, glow) {
  material.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <emissivemap_fragment>",
      `#include <emissivemap_fragment>\n totalEmissiveRadiance += vColor.rgb * ${glow.toFixed(3)};`,
    );
  };
  material.customProgramCacheKey = () => `story-${glow.toFixed(3)}`;
  return material;
}

// a red cell: a disc dented in the middle on both sides (the Evans and Fung shape), turned round its axis
function cellGeometry() {
  const height = (x) => 0.5 * Math.sqrt(Math.max(0, 1 - x * x)) * (0.207 + 2.003 * x * x - 1.123 * x ** 4);
  const steps = 10;
  const points = [];
  for (let i = 0; i <= steps; i++) points.push(new THREE.Vector2(i / steps, height(i / steps)));
  for (let i = steps - 1; i >= 0; i--) points.push(new THREE.Vector2(i / steps, -height(i / steps)));
  return new THREE.LatheGeometry(points, 20);
}

function deviceIsSlow() {
  return matchMedia("(pointer: coarse)").matches;
}

export class StoryScene {
  constructor(canvas, { theme = "dark", onLabels = () => {} } = {}) {
    this.canvas = canvas;
    this.theme = theme;
    this.onLabels = onLabels;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
    this.pixelRatio = Math.min(devicePixelRatio || 1, 2);
    this.renderer.setPixelRatio(this.pixelRatio);
    this.renderer.toneMapping = theme === "dark" ? THREE.NeutralToneMapping : THREE.NoToneMapping;
    if (deviceIsSlow()) this.renderer.transmissionResolutionScale = 0.5;
    this.quality = ["no glass", "ratio15", "ratio1"];
    this.frameMs = [];

    this.scene = new THREE.Scene();
    this.scene.background = color("--hero");
    this.camera = new THREE.PerspectiveCamera(FOV, WIDTH / HEIGHT, 1, 200);
    this.camera.position.z = (HEIGHT / 2) / Math.tan(THREE.MathUtils.degToRad(FOV / 2));
    this.scene.environment = this.studio();
    this.keyLight = new THREE.PointLight(color("--strip-main"), parseFloat(token("--light-key")) * 40, 0, 1.6);
    this.keyLight.position.set(-5, 7, 9);
    this.warmLight = new THREE.PointLight(color("--strip-warm"), parseFloat(token("--light-warm")) * 30, 0, 1.6);
    this.warmLight.position.set(6, -5, 7);
    this.scene.add(this.keyLight, this.warmLight);

    this.glow = parseFloat(token("--glass-glow"));
    this.world = new THREE.Group();
    this.scene.add(this.world);
    this.clock = 0;
    this.step = 0;
    this.stepClock = 0;
    this.perpetratorIn = false;
    this.running = false;
    this.token = 0;
    this.visible = true;
    this.fill = NORMAL_UP;
    this.particleNext = 0;

    new ResizeObserver(() => this.resize()).observe(canvas);
    new IntersectionObserver(([entry]) => { this.visible = entry.isIntersecting; }).observe(canvas);
    this.resize();
  }

  // the app starts it when the Lab opens and stops it when another tab opens. a token, so a quick stop and start
  // never leaves two loops running
  start() {
    if (this.running) return;
    this.running = true;
    this.last = performance.now();
    const token = ++this.token;
    const tick = (now) => {
      if (!this.running || token !== this.token) return;
      requestAnimationFrame(tick);
      this.loop(now);
    };
    requestAnimationFrame(tick);
  }

  // the colours are read when a story is built, so a new theme builds the same story again
  setTheme(theme) {
    this.theme = theme;
    this.renderer.toneMapping = theme === "dark" ? THREE.NeutralToneMapping : THREE.NoToneMapping;
    this.scene.background = color("--hero");
    this.scene.environment?.dispose();
    this.scene.environment = this.studio();
    this.keyLight.color = color("--strip-main");
    this.keyLight.intensity = parseFloat(token("--light-key")) * 40;
    this.warmLight.color = color("--strip-warm");
    this.warmLight.intensity = parseFloat(token("--light-warm")) * 30;
    this.glow = parseFloat(token("--glass-glow"));
    if (!this.story) return;
    const step = this.step;
    this.setStory(this.story, ...this.raws);
    this.setStep(step);
  }

  stop() {
    this.running = false;
  }

  studio() {
    const room = new THREE.Scene();
    room.add(new THREE.Mesh(new THREE.SphereGeometry(50, 24, 12), new THREE.MeshBasicMaterial({ color: color("--studio-room"), side: THREE.BackSide })));
    const strip = (name, power, x, y, z, w, h) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: color(name).multiplyScalar(power), side: THREE.DoubleSide }));
      mesh.position.set(x, y, z);
      mesh.lookAt(0, 0, 0);
      room.add(mesh);
    };
    strip("--strip-cool", 12, -20, 6, 16, 5, 40);
    strip("--strip-warm", 10, 22, -4, 10, 4, 40);
    strip("--strip-main", 8, 2, 26, 12, 22, 4);
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    const texture = pmrem.fromScene(room, 0.012).texture;
    pmrem.dispose();
    return texture;
  }

  resize() {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (!width || !height) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  // a new pair. a molecule without a structure gets a plain glass bead, the story still works
  setStory(story, victimRaw, perpetratorRaw) {
    // the last pair leaves the graphics memory as well
    const old = new Set();
    this.world.traverse((o) => { if (o.geometry) old.add(o.geometry); if (o.material) old.add(o.material); });
    old.forEach((thing) => thing.dispose());
    this.world.clear();
    this.raws = [victimRaw, perpetratorRaw];
    this.story = story;
    this.reduced = false;
    const placeholder = { atoms: [["C", 0, 0, 0]], bonds: [] };
    const victim = centred(victimRaw ?? placeholder);
    const perpetrator = centred(perpetratorRaw ?? placeholder);

    this.heroMaterial = withBody(new THREE.MeshPhysicalMaterial({
      vertexColors: true, roughness: 0.05, transmission: 1, thickness: 0.5, ior: 1.5, iridescence: 0.25,
      iridescenceIOR: 1.3, iridescenceThicknessRange: [180, 420], envMapIntensity: this.theme === "dark" ? 1.8 : 1.1,
    }), this.glow * 3);
    const detail = deviceIsSlow() ? 12 : 18;
    this.victimHero = new THREE.Mesh(moleculeGeometry(victim, detail, 1.25), this.heroMaterial);
    this.perpetratorHero = new THREE.Mesh(moleculeGeometry(perpetrator, detail, 1.25), this.heroMaterial);
    this.perpetratorHero.position.set(HERO_X, HERO_Y, 0); // it waits at its place, it does not fly in from the middle
    this.perpetratorFrom = this.perpetratorHero.position.clone();
    this.sizeFrom = HERO_RADIUS;
    this.moveClock = 0;
    this.doorY = 0;
    this.world.add(this.victimHero, this.perpetratorHero);

    const copyMaterial = withBody(new THREE.MeshPhysicalMaterial({
      vertexColors: true, roughness: 0.14, clearcoat: 0.8, envMapIntensity: this.theme === "dark" ? 1.7 : 1.05,
    }), this.glow * 2.5);
    // chunkier than real on purpose, at this size true proportions are only a thin line
    this.copies = new THREE.InstancedMesh(moleculeGeometry(victim, 6, 2.3), copyMaterial, VESSEL_MAX);
    this.copies.frustumCulled = false;
    this.world.add(this.copies);

    this.victimAtoms = victim.atoms.map((a) => ({ at: a.at.clone().multiplyScalar(1 / victim.radius), tint: color(ATOM_TOKENS[a.element] ?? "--atom-cl") }));
    this.particles = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 6, 4), new THREE.MeshBasicMaterial(), PARTICLES);
    this.particles.frustumCulled = false;
    this.particles.setColorAt(0, color("--atom-c"));
    this.world.add(this.particles);
    this.bits = Array.from({ length: PARTICLES }, () => ({ life: 0, max: 1, p: new THREE.Vector3(), v: new THREE.Vector3(), r: 0.1 }));

    this.gateMaterial = new THREE.MeshPhysicalMaterial({
      color: color("--accent"), emissive: color("--accent"), emissiveIntensity: this.theme === "dark" ? 0.55 : 0.2, roughness: 0.2, clearcoat: 1,
    });
    this.gates = [];
    this.buildPassage();
    this.buildVessel();
    if (this.noGlass) this.plainGlass(); // a phone that was too slow stays on the cheaper look for every pair
    this.reset();
  }

  buildPassage() {
    if (this.story.kind === "transporter") {
      // a wall with one door in it, blood on the left
      const wallMaterial = new THREE.MeshPhysicalMaterial({
        color: color("--text-secondary"), roughness: 0.3, transparent: true, opacity: 0.32, emissive: color("--text-secondary"), emissiveIntensity: 0.15,
      });
      const piece = (height, y) => {
        const mesh = new THREE.Mesh(new THREE.BoxGeometry(0.42, height, 1.1), wallMaterial);
        mesh.position.set(GATE_X, y, 0);
        return mesh;
      };
      const gap = 2.6;
      const top = 0.25;
      const bottom = -HEIGHT / 2 - 0.5;
      this.wall = new THREE.Group();
      this.wall.add(piece(top - (LANE_Y + gap / 2), (top + LANE_Y + gap / 2) / 2), piece(LANE_Y - gap / 2 - bottom, (LANE_Y - gap / 2 + bottom) / 2));
      this.door = new THREE.Mesh(new THREE.BoxGeometry(0.34, gap, 1), this.gateMaterial);
      this.door.position.set(GATE_X, LANE_Y + gap / 2, 0);
      this.doorGap = gap;
      this.wall.add(this.door);
      this.world.add(this.wall);
      this.gates = [{ x: GATE_X, y: LANE_Y, wait: 0, scale: 1 }];
      return;
    }
    const torus = new THREE.TorusGeometry(GATE_RADIUS, 0.15, 12, 40);
    const rows = [LANE_Y, LANE_Y + 2.75, LANE_Y - 2.75];
    this.gateRows = rows;
    this.gates = rows.map((y, i) => {
      const mesh = new THREE.Mesh(torus, this.gateMaterial);
      mesh.position.set(GATE_X, y, 0);
      mesh.rotation.y = 1.05;
      this.world.add(mesh);
      return { mesh, x: GATE_X, y, wait: 0, scale: i === 0 ? 1 : 0, extra: i > 0 };
    });
  }

  // a vessel cut open along the front, like a textbook drawing, with red cells and the drug flowing through
  buildVessel() {
    this.vessel = new THREE.Group();
    this.vessel.position.set(0, -1.75, -0.4);
    this.vessel.rotation.set(-0.38, 0, 0.36);
    const inner = VESSEL_R * 0.84;
    const tube = (radius) => {
      const g = new THREE.CylinderGeometry(radius, radius, VESSEL_LENGTH, 72, 1, true, VESSEL_OPEN, Math.PI * 2 - VESSEL_OPEN * 2);
      g.rotateZ(-Math.PI / 2);
      return g;
    };
    const wallColour = color("--vessel-wall");
    const outside = new THREE.Mesh(tube(VESSEL_R), new THREE.MeshPhysicalMaterial({
      color: wallColour, roughness: 0.38, clearcoat: 0.7, clearcoatRoughness: 0.25, side: THREE.DoubleSide,
      emissive: wallColour, emissiveIntensity: this.theme === "dark" ? 0.18 : 0.05,
    }));
    const insideColour = wallColour.clone().lerp(color("--hero"), 0.35);
    const inside = new THREE.Mesh(tube(inner), new THREE.MeshPhysicalMaterial({
      color: insideColour, roughness: 0.6, side: THREE.DoubleSide, emissive: insideColour, emissiveIntensity: this.theme === "dark" ? 0.12 : 0.02,
    }));
    this.vessel.add(outside, inside);

    // the cut edges show the layers of the wall
    const lining = new THREE.MeshPhysicalMaterial({ color: color("--vessel-lining"), roughness: 0.45, emissive: color("--vessel-lining"), emissiveIntensity: this.theme === "dark" ? 0.12 : 0 });
    const shine = new THREE.MeshBasicMaterial({ color: color("--strip-main") });
    for (const angle of [VESSEL_OPEN, Math.PI * 2 - VESSEL_OPEN]) {
      const layer = (from, to, material) => {
        const middle = (from + to) / 2;
        const mesh = new THREE.Mesh(new THREE.BoxGeometry(VESSEL_LENGTH, to - from, 0.035), material);
        mesh.position.set(0, -middle * Math.sin(angle), middle * Math.cos(angle));
        mesh.rotation.x = angle + Math.PI / 2;
        return mesh;
      };
      this.vessel.add(layer(inner + 0.07, VESSEL_R, lining), layer(inner, inner + 0.07, shine));
    }

    this.vesselInner = inner;
    this.cells = new THREE.InstancedMesh(cellGeometry(), new THREE.MeshPhysicalMaterial({
      color: color("--vessel-cell"), roughness: 0.32, clearcoat: 0.6, sheen: 0.4, sheenColor: color("--vessel-lining"),
      emissive: color("--vessel-cell"), emissiveIntensity: this.theme === "dark" ? 0.16 : 0.03,
    }), CELLS);
    this.cells.frustumCulled = false;
    this.cellState = Array.from({ length: CELLS }, (_, i) => ({
      ...this.inVessel(0.46, i),
      u: -VESSEL_LENGTH / 2 + ((i * 0.618) % 1) * VESSEL_LENGTH,
      speed: 0.8 + ((i * 0.37) % 1) * 0.4,
      axis: new THREE.Euler(i * 1.3, i * 0.7, i * 2.1),
      turn: 0.3 + (i % 4) * 0.15,
    }));
    this.vessel.add(this.cells);

    // two more vessels far behind, out of focus, so it reads as a body and not a pipe
    const far = new THREE.MeshStandardMaterial({ color: color("--vessel-far"), roughness: 0.9 });
    const curve = (points) => new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(([x, y, z]) => new THREE.Vector3(x, y, z))), 40, 1.3, 16), far);
    this.vesselFar = new THREE.Group();
    this.vesselFar.add(
      curve([[-16, 9, -22], [-6, 5, -24], [2, 8, -22], [14, 4, -24]]),
      curve([[-14, -12, -26], [-4, -3, -24], [6, -9, -26], [16, -4, -24]]),
    );

    this.vesselRoot = new THREE.Group();
    this.vesselRoot.add(this.vessel, this.vesselFar);
    this.vesselRoot.visible = false;
    this.world.add(this.vesselRoot);
    this.vesselRoot.updateMatrixWorld(true);
  }

  // a random place in the round inside of the vessel, the same every time for the same seed
  inVessel(size, seed) {
    const room = this.vesselInner - size - 0.1;
    const radius = room * Math.sqrt(((seed * 0.754877) % 1));
    const angle = ((seed * 0.569840) % 1) * Math.PI * 2;
    return { ry: -radius * Math.sin(angle), rz: radius * Math.cos(angle) };
  }

  // the molecules already in the blood when step three opens, spread along the whole vessel
  seedVessel() {
    const count = Math.max(1, Math.round(VESSEL_MAX * this.target().normal));
    this.flow = Array.from({ length: count }, (_, i) => this.vesselMolecule(-VESSEL_LENGTH / 2 + ((i + 0.5) / count) * VESSEL_LENGTH, i + 1));
    this.vesselWait = 0;
  }

  vesselMolecule(u, seed) {
    return { u, ...this.inVessel(0.8, seed * 1.37 + 0.2), seed, spin: seed, turn: 0.4 + (seed % 3) * 0.15, size: 0.82, speed: 0.9 + ((seed * 0.29) % 1) * 0.3 };
  }

  target() {
    const { story } = this;
    const ratio = story.ratio;
    const normal = ratio === null ? NORMAL_UP : story.up ? NORMAL_UP : NORMAL_DOWN;
    const after = ratio === null ? TRANSPORTER_FILL : clamp(normal * ratio, 0.03, 0.97);
    return { normal, after, spills: ratio !== null && normal * ratio > 1 };
  }

  reset() {
    this.flow = [];
    this.spawnWait = 0;
    this.gates.forEach((g) => { g.wait = 0; });
    this.bits.forEach((b) => { b.life = 0; });
    this.fill = this.target().normal;
    this.drawCopies();
  }

  setStep(step) {
    if (step === 0 || this.step === 2) this.reset();
    this.step = step;
    this.stepClock = 0;
    this.perpetratorIn = step === 1;
    this.perpetratorFrom = this.perpetratorHero?.position.clone();
    this.moveClock = 0;
    if (step === 2) {
      this.fill = this.target().normal;
      this.bits.forEach((b) => { b.life = 0; });
      this.seedVessel();
    }
  }

  setPerpetrator(inside) {
    this.perpetratorIn = inside;
    this.perpetratorFrom = this.perpetratorHero.position.clone();
    this.moveClock = 0;
  }

  // how long one molecule takes at each gate
  serviceTime() {
    if (this.step === 0 || !this.perpetratorIn || this.moveClock < 1.1) return FREE_GATE_S;
    if (this.story.kind === "transporter") return Infinity;
    return this.story.ratio >= 1 ? ARRIVAL_S * this.story.ratio : FREE_GATE_S * this.story.ratio;
  }

  spawn() {
    if (this.flow.length >= COPIES) return;
    const open = this.flow.filter((v) => !v.gone).length;
    if (open >= COPIES) return;
    this.flow.push({ x: -WIDTH / 2 - 1, y: LANE_Y + (Math.random() - 0.5) * 1.6, spin: Math.random() * 6, turn: 0.4 + Math.random() * 0.5, seed: Math.random() * 10, through: false });
  }

  activeGates() {
    const extras = this.story.kind === "induce" && this.step === 1 && this.perpetratorIn && this.moveClock > 1.1;
    return this.gates.filter((g) => !g.extra || extras);
  }

  burst(v) {
    // the molecule falls apart into its own atoms, in their own colours
    const scale = COPY_RADIUS;
    const atoms = this.victimAtoms;
    const howMany = Math.min(atoms.length, 12);
    for (let k = 0; k < howMany; k++) {
      const atom = atoms[Math.floor((k * atoms.length) / howMany)];
      const bit = this.bits[this.particleNext];
      this.particleNext = (this.particleNext + 1) % PARTICLES;
      bit.p.set(v.x + atom.at.x * scale, v.y + atom.at.y * scale, atom.at.z * scale);
      bit.v.set(1 + Math.random() * 2.4, (Math.random() - 0.5) * 2.2, (Math.random() - 0.5) * 1.2);
      bit.max = 0.9 + Math.random() * 0.9;
      bit.life = bit.max;
      bit.r = 0.07 + Math.random() * 0.05;
      this.particles.setColorAt(this.bits.indexOf(bit), atom.tint);
    }
    this.particles.instanceColor.needsUpdate = true;
  }

  simulateFlow(dt) {
    const service = this.serviceTime();
    this.spawnWait -= dt;
    if (this.spawnWait <= 0) {
      this.spawn();
      this.spawnWait = ARRIVAL_S;
    }
    const gates = this.activeGates();
    gates.forEach((g) => { g.wait -= dt; });
    const queue = this.flow.filter((v) => !v.through);
    queue.forEach((v, k) => {
      const gate = gates[k % gates.length];
      const place = Math.floor(k / gates.length);
      // a single file while it moves, three rows once it piles up in front of a blocked gate
      const row = gates.length === 1 ? place % 3 : 0;
      const column = gates.length === 1 ? Math.floor(place / 3) : place;
      const offset = gates.length === 1 && place > 0 ? [0, 1.2, -1.2][row] : 0;
      const tx = gate.x - 0.75 - (gates.length === 1 && place > 0 ? 0.95 : 0) - column * 1.25;
      const ty = gate.y + offset + Math.sin(this.clock * 1.6 + v.seed) * 0.05;
      v.x += clamp(tx - v.x, -SPEED * dt, SPEED * dt);
      v.y += (ty - v.y) * Math.min(1, dt * 3);
      v.gate = gate;
      v.atFront = place === 0 && Math.abs(tx - v.x) < 0.15 && Math.abs(ty - v.y) < 0.6;
    });
    for (const v of queue) {
      if (!v.atFront || v.gate.wait > 0) continue;
      v.gate.wait = service;
      if (this.story.kind === "transporter") v.through = true;
      else {
        this.burst(v);
        v.gone = true;
      }
    }
    for (const v of this.flow) {
      if (!v.through) continue;
      v.x += SPEED * 1.1 * dt;
      v.y += (LANE_Y - v.y) * Math.min(1, dt * 3);
      if (v.x > WIDTH / 2 + 1) v.gone = true;
    }
    this.flow = this.flow.filter((v) => !v.gone);
    this.flow.forEach((v) => { v.spin += v.turn * dt; });
  }

  drawCopies() {
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const e = new THREE.Euler();
    const p = new THREE.Vector3();
    const s = new THREE.Vector3();
    for (let i = 0; i < this.copies.count; i++) {
      const v = this.flow[i];
      if (!v) {
        m.makeScale(0, 0, 0);
      } else {
        e.set(v.spin * 0.6, v.spin, 0);
        p.set(v.x, v.y, v.z ?? 0);
        s.setScalar(v.size ?? COPY_RADIUS);
        m.compose(p, q.setFromEuler(e), s);
      }
      this.copies.setMatrixAt(i, m);
    }
    this.copies.instanceMatrix.needsUpdate = true;
  }

  drawBits(dt) {
    const m = new THREE.Matrix4();
    this.bits.forEach((b, i) => {
      if (b.life > 0) {
        b.life -= dt;
        b.p.addScaledVector(b.v, dt);
        b.v.multiplyScalar(1 - dt * 0.6);
      }
      const r = b.life > 0 ? b.r * clamp(b.life / b.max, 0, 1) ** 0.5 : 0;
      this.particles.setMatrixAt(i, m.makeScale(r, r, r).setPosition(b.p));
    });
    this.particles.instanceMatrix.needsUpdate = true;
  }

  // the blood fills up with the drug or loses it. new molecules flow in from the left, cleared ones fall apart
  simulateVessel(dt) {
    const { after } = this.target();
    this.fill += (after - this.fill) * Math.min(1, dt * 0.6);
    const wanted = Math.max(1, Math.round(VESSEL_MAX * this.fill));
    this.vesselWait -= dt;
    if (this.vesselWait <= 0 && this.flow.length !== wanted) {
      this.vesselWait = 0.22;
      if (this.flow.length < wanted) {
        this.seedCount = (this.seedCount ?? 50) + 1;
        this.flow.push(this.vesselMolecule(-6.6 - Math.random() * 0.8, this.seedCount));
      } else {
        // the one most in view goes, so you see it happen
        const gone = this.flow.reduce((best, v) => (Math.abs(v.u) < Math.abs(best.u) ? v : best));
        this.burst(gone);
        this.flow = this.flow.filter((v) => v !== gone);
      }
    }
    const at = new THREE.Vector3();
    const matrix = this.vessel.matrixWorld;
    for (const v of this.flow) {
      v.u += VESSEL_SPEED * v.speed * dt;
      if (v.u > VESSEL_LENGTH / 2) v.u -= VESSEL_LENGTH;
      at.set(v.u, v.ry + Math.sin(this.clock * 1.1 + v.seed) * 0.08, v.rz).applyMatrix4(matrix);
      v.x = at.x;
      v.y = at.y;
      v.z = at.z;
      v.spin += v.turn * dt;
    }
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const p = new THREE.Vector3();
    const size = new THREE.Vector3(0.46, 0.46, 0.46);
    this.cellState.forEach((c, i) => {
      c.u += VESSEL_SPEED * c.speed * dt;
      if (c.u > VESSEL_LENGTH / 2) c.u -= VESSEL_LENGTH;
      c.axis.x += c.turn * dt;
      c.axis.z += c.turn * 0.6 * dt;
      m.compose(p.set(c.u, c.ry, c.rz), q.setFromEuler(c.axis), size);
      this.cells.setMatrixAt(i, m);
    });
    this.cells.instanceMatrix.needsUpdate = true;
  }

  placeActors(dt) {
    const { story, step } = this;
    this.moveClock += dt;
    this.victimHero.rotation.y = this.clock * 0.35;
    this.victimHero.rotation.x = 0.25 + Math.sin(this.clock * 0.4) * 0.12;
    this.perpetratorHero.rotation.y = -this.clock * 0.3;
    this.perpetratorHero.rotation.x = 0.2 + Math.cos(this.clock * 0.35) * 0.12;
    const float = Math.sin(this.clock * 0.8) * 0.07;

    const vesselShown = step === 2;
    this.victimHero.position.set(-HERO_X, HERO_Y + float, 0);
    this.victimHero.scale.setScalar(HERO_RADIUS * (vesselShown ? 0 : 1));

    let target;
    let size;
    if (!this.perpetratorIn || step !== 1) {
      target = new THREE.Vector3(HERO_X, HERO_Y - float, 0);
      size = HERO_RADIUS;
    } else if (story.kind === "induce") {
      target = new THREE.Vector3(3.55, LANE_Y, 0.2);
      size = 0.92;
    } else if (story.kind === "transporter") {
      target = new THREE.Vector3(GATE_X + 1.35, LANE_Y, 0.2);
      size = 0.92;
    } else {
      target = new THREE.Vector3(GATE_X, LANE_Y, 0.15);
      size = 0.92;
    }
    const t = easeOut(this.moveClock / 1.1);
    this.perpetratorHero.position.lerpVectors(this.perpetratorFrom ?? target, target, t);
    const from = this.sizeFrom ?? HERO_RADIUS;
    this.perpetratorHero.scale.setScalar(vesselShown ? 0 : from + (size - from) * t);
    if (t >= 1) this.sizeFrom = size;

    const blocked = step === 1 && this.perpetratorIn && this.moveClock > 0.8;
    const gateColor = blocked && story.kind !== "induce" ? "--jewel-pink" : "--accent";
    this.gateMaterial.color.lerp(color(gateColor), Math.min(1, dt * 5));
    this.gateMaterial.emissive.lerp(color(gateColor), Math.min(1, dt * 5));

    if (story.kind === "transporter") {
      this.wall.visible = !vesselShown;
      const closed = blocked ? 1 : 0;
      this.doorY = (this.doorY ?? 0) + (closed - (this.doorY ?? 0)) * Math.min(1, dt * 4);
      // it comes down out of the wall, open there is nothing in the way
      const length = Math.max(0.001, this.doorY);
      this.door.scale.y = length;
      this.door.position.y = LANE_Y + (this.doorGap / 2) * (1 - length);
    } else {
      const extras = story.kind === "induce" && blocked;
      for (const g of this.gates) {
        const want = vesselShown ? 0 : !g.extra || extras ? 1 : 0;
        g.scale += (want - g.scale) * Math.min(1, dt * 5);
        g.mesh.scale.setScalar(Math.max(0.0001, g.scale));
        g.mesh.visible = g.scale > 0.01;
      }
    }
    this.vesselRoot.visible = vesselShown;
  }

  update(dt) {
    this.clock += dt;
    this.stepClock += dt;
    this.placeActors(dt);
    if (this.step === 2) this.simulateVessel(dt);
    else this.simulateFlow(dt);
    this.drawCopies();
    this.drawBits(dt);
  }

  // jumps ahead to where a step has settled, for the still frames and for screenshots
  settle(step) {
    const seconds = [6, 24, 12][step];
    this.setStep(step);
    for (let t = 0; t < seconds; t += 1 / 30) this.update(1 / 30);
  }

  project(x, y, z = 0) {
    const v = new THREE.Vector3(x, y, z).project(this.camera);
    return { x: ((v.x + 1) / 2) * 100, y: ((1 - v.y) / 2) * 100 };
  }

  // where the words go, in percent of the canvas. the words themselves are html, so they stay sharp
  labels() {
    const { story, step } = this;
    const out = [];
    if (step < 2) {
      out.push({ id: "victim", at: this.project(-HERO_X, HERO_Y - HERO_RADIUS - 0.42) });
      // the name goes along with the molecule, above the gate or the door once it is there
      const arrived = this.perpetratorIn && step === 1 && this.moveClock > 0.9;
      const place = !arrived ? [HERO_X, HERO_Y - HERO_RADIUS - 0.42]
        : story.kind === "induce" ? [3.55, LANE_Y + 1.25]
          : story.kind === "transporter" ? [GATE_X + 1.75, LANE_Y + 1.25] : [GATE_X, LANE_Y + GATE_RADIUS + 0.45];
      if (!this.perpetratorIn || step !== 1 || arrived) out.push({ id: "perpetrator", at: this.project(...place) });
      if (story.kind === "transporter") {
        out.push({ id: "target", at: this.project(GATE_X, 0.68) });
        out.push({ id: "blood", at: this.project(-3.2, LANE_Y - 2.9) });
        out.push({ id: "other", at: this.project(3.2, LANE_Y - 2.9) });
      } else {
        // once there are more gates the name goes above them all
        const many = story.kind === "induce" && arrived;
        out.push({ id: "target", at: this.project(GATE_X, many ? LANE_Y + 2.75 + GATE_RADIUS + 0.45 : LANE_Y - GATE_RADIUS - 0.45) });
      }
    } else {
      const blood = new THREE.Vector3(-2.6, VESSEL_R + 0.55, 0).applyMatrix4(this.vessel.matrixWorld);
      out.push({ id: "blood", at: this.project(blood.x, blood.y, blood.z) });
    }
    return out;
  }

  render() {
    this.renderer.render(this.scene, this.camera);
    this.onLabels(this.labels());
  }

  // real glass renders the whole scene behind it again, a slow phone gets plain shiny atoms instead
  plainGlass() {
    this.heroMaterial.transmission = 0;
    this.heroMaterial.roughness = 0.12;
    this.heroMaterial.clearcoat = 0.8;
    this.heroMaterial.needsUpdate = true;
  }

  watchSpeed(ms) {
    if (!this.quality.length) return;
    this.frameMs.push(ms);
    const total = this.frameMs.reduce((sum, v) => sum + v, 0);
    if (total < CHECK_EVERY_MS || this.frameMs.length < 3) return;
    const average = total / this.frameMs.length;
    this.frameMs.length = 0;
    if (average <= SLOW_FRAME_MS) return;
    const step = this.quality.shift();
    if (step === "no glass") {
      this.noGlass = true;
      this.plainGlass();
    } else {
      this.pixelRatio = Math.min(this.pixelRatio, step === "ratio15" ? 1.5 : 1);
      this.renderer.setPixelRatio(this.pixelRatio);
      this.resize();
    }
    this.canvas.dataset.quality = step;
  }

  loop(now) {
    const elapsed = now - this.last;
    this.last = now;
    if (!this.visible || document.hidden || !this.story) return;
    this.update(Math.min(elapsed, 80) / 1000);
    this.render();
    this.frames = (this.frames ?? 0) + 1;
    // a gap this long is the browser pausing a window nobody looks at, not a slow phone
    if (this.frames > 8 && elapsed < 250) this.watchSpeed(elapsed);
  }

  // one frame now, as a picture. has to be read in the same tick as the render
  still(step) {
    this.settle(step);
    this.renderer.render(this.scene, this.camera);
    const url = this.canvas.toDataURL("image/png");
    this.onLabels(this.labels());
    return url;
  }
}
