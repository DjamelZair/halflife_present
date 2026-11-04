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
const NORMAL_UP = 0.2; // the fill of the glass before an interaction that raises it, so 5x is exactly full
const NORMAL_DOWN = 0.62;
const TRANSPORTER_FILL = 0.56; // no number for these, so it only shows the direction

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
    const key = new THREE.PointLight(color("--strip-main"), parseFloat(token("--light-key")) * 40, 0, 1.6);
    key.position.set(-5, 7, 9);
    const warm = new THREE.PointLight(color("--strip-warm"), parseFloat(token("--light-warm")) * 30, 0, 1.6);
    warm.position.set(6, -5, 7);
    this.scene.add(key, warm);

    this.glow = parseFloat(token("--glass-glow"));
    this.world = new THREE.Group();
    this.scene.add(this.world);
    this.clock = 0;
    this.step = 0;
    this.stepClock = 0;
    this.perpetratorIn = false;
    this.running = true;
    this.visible = true;
    this.fill = NORMAL_UP;
    this.particleNext = 0;

    new ResizeObserver(() => this.resize()).observe(canvas);
    new IntersectionObserver(([entry]) => { this.visible = entry.isIntersecting; }).observe(canvas);
    this.resize();
    this.loop = this.loop.bind(this);
  }

  start() {
    this.running = true;
    this.last = performance.now();
    requestAnimationFrame(this.loop);
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
    this.world.clear();
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
    this.copies = new THREE.InstancedMesh(moleculeGeometry(victim, 6, 2.3), copyMaterial, COPIES);
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
    this.buildGlass();
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

  buildGlass() {
    this.glass = new THREE.Group();
    const radius = 2.5;
    const height = 7.4;
    this.glassBottom = -5.2;
    this.glassHeight = height;
    const wall = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius * 0.92, height, 48, 1, true), new THREE.MeshPhysicalMaterial({
      color: color("--strip-main"), roughness: 0.08, transparent: true, opacity: 0.2, envMapIntensity: 2, side: THREE.DoubleSide, depthWrite: false,
    }));
    wall.position.y = this.glassBottom + height / 2;
    const rim = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.06, 10, 60), new THREE.MeshPhysicalMaterial({ color: color("--strip-main"), roughness: 0.1, envMapIntensity: 2 }));
    rim.rotation.x = Math.PI / 2.2;
    rim.position.y = this.glassBottom + height;
    this.liquid = new THREE.Mesh(new THREE.CylinderGeometry(radius * 0.96, radius * 0.9, 1, 48), new THREE.MeshPhysicalMaterial({
      color: color(this.story.up ? "--chart-after" : "--chart-before"), roughness: 0.18, transparent: true, opacity: 0.62, depthWrite: false,
      emissive: color(this.story.up ? "--chart-after" : "--chart-before"), emissiveIntensity: this.theme === "dark" ? 0.3 : 0.1,
    }));
    this.mark = new THREE.Mesh(new THREE.BoxGeometry(radius * 2.15, 0.05, 0.05), new THREE.MeshBasicMaterial({ color: color("--text") }));
    this.glass.add(this.liquid, wall, rim, this.mark);
    this.glass.visible = false;
    this.world.add(this.glass);
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
    for (let i = 0; i < COPIES; i++) {
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

  // the molecules inside the glass
  simulateGlass(dt) {
    const { after, normal, spills } = this.target();
    this.fill += (after - this.fill) * Math.min(1, dt * 0.95);
    const level = this.glassBottom + this.fill * this.glassHeight;
    this.liquid.scale.y = Math.max(0.01, this.fill * this.glassHeight);
    this.liquid.position.y = this.glassBottom + (this.fill * this.glassHeight) / 2;
    this.mark.position.y = this.glassBottom + normal * this.glassHeight;
    const wanted = Math.max(1, Math.round(COPIES * clamp(this.fill / 0.9, 0, 1)));
    while (this.flow.length < wanted) {
      const i = this.flow.length;
      const a = (i * 2.4) % (Math.PI * 2);
      this.flow.push({ gx: Math.cos(a) * (0.5 + ((i * 0.37) % 1) * 1.6), gz: Math.sin(a) * 0.7, gh: ((i * 0.618) % 1), seed: i, spin: i, turn: 0.3 + (i % 3) * 0.15, size: 0.5 });
    }
    this.flow.length = Math.min(this.flow.length, wanted);
    for (const v of this.flow) {
      if (v.gx === undefined) { v.gx = v.x > 2 ? 2 : Math.max(-2, (v.x ?? 0) / 2); v.gz = 0; v.gh = (v.seed % 1); v.size = 0.5; }
      const tx = v.gx + Math.sin(this.clock * 0.7 + v.seed) * 0.08;
      const ty = this.glassBottom + 0.45 + v.gh * Math.max(0.05, this.fill * this.glassHeight - 0.9) + Math.sin(this.clock + v.seed) * 0.06;
      v.x = v.x === undefined ? tx : v.x + (tx - v.x) * Math.min(1, dt * 2.5);
      v.y = v.y === undefined ? ty : v.y + (ty - v.y) * Math.min(1, dt * 2.5);
      v.z = v.gz;
      v.spin += v.turn * dt;
    }
    if (spills && this.fill > after - 0.03 && Math.random() < dt * 9) {
      // more than the glass holds, the number says how much
      const bit = this.bits[this.particleNext];
      const side = Math.random() < 0.5 ? -1 : 1;
      bit.p.set(side * 2.5, level + 0.1, 0.4);
      bit.v.set(side * (0.3 + Math.random() * 0.5), -0.5 - Math.random(), 0);
      bit.max = 1.6;
      bit.life = bit.max;
      bit.r = 0.09;
      this.particles.setColorAt(this.particleNext, new THREE.Color(this.liquid.material.color));
      this.particles.instanceColor.needsUpdate = true;
      this.particleNext = (this.particleNext + 1) % PARTICLES;
    }
  }

  placeActors(dt) {
    const { story, step } = this;
    this.moveClock += dt;
    this.victimHero.rotation.y = this.clock * 0.35;
    this.victimHero.rotation.x = 0.25 + Math.sin(this.clock * 0.4) * 0.12;
    this.perpetratorHero.rotation.y = -this.clock * 0.3;
    this.perpetratorHero.rotation.x = 0.2 + Math.cos(this.clock * 0.35) * 0.12;
    const float = Math.sin(this.clock * 0.8) * 0.07;

    const glassShown = step === 2;
    this.victimHero.position.set(-HERO_X, HERO_Y + float, 0);
    this.victimHero.scale.setScalar(HERO_RADIUS * (glassShown ? 0 : 1));

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
    this.perpetratorHero.scale.setScalar(glassShown ? 0 : from + (size - from) * t);
    if (t >= 1) this.sizeFrom = size;

    const blocked = step === 1 && this.perpetratorIn && this.moveClock > 0.8;
    const gateColor = blocked && story.kind !== "induce" ? "--jewel-pink" : "--accent";
    this.gateMaterial.color.lerp(color(gateColor), Math.min(1, dt * 5));
    this.gateMaterial.emissive.lerp(color(gateColor), Math.min(1, dt * 5));

    if (story.kind === "transporter") {
      this.wall.visible = !glassShown;
      const closed = blocked ? 1 : 0;
      this.doorY = (this.doorY ?? 0) + (closed - (this.doorY ?? 0)) * Math.min(1, dt * 4);
      // it comes down out of the wall, open there is nothing in the way
      const length = Math.max(0.001, this.doorY);
      this.door.scale.y = length;
      this.door.position.y = LANE_Y + (this.doorGap / 2) * (1 - length);
    } else {
      const extras = story.kind === "induce" && blocked;
      for (const g of this.gates) {
        const want = glassShown ? 0 : !g.extra || extras ? 1 : 0;
        g.scale += (want - g.scale) * Math.min(1, dt * 5);
        g.mesh.scale.setScalar(Math.max(0.0001, g.scale));
        g.mesh.visible = g.scale > 0.01;
      }
    }
    this.glass.visible = glassShown;
  }

  update(dt) {
    this.clock += dt;
    this.stepClock += dt;
    this.placeActors(dt);
    if (this.step === 2) this.simulateGlass(dt);
    else this.simulateFlow(dt);
    this.drawCopies();
    this.drawBits(dt);
  }

  // jumps ahead to where a step has settled, for the still frames and for screenshots
  settle(step) {
    const seconds = [6, 24, 8][step];
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
      out.push({ id: "normal", at: this.project(-3.75, this.glassBottom + this.target().normal * this.glassHeight) });
    }
    return out;
  }

  render() {
    this.renderer.render(this.scene, this.camera);
    this.onLabels(this.labels());
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
      this.heroMaterial.transmission = 0;
      this.heroMaterial.roughness = 0.12;
      this.heroMaterial.clearcoat = 0.8;
      this.heroMaterial.needsUpdate = true;
    } else {
      this.pixelRatio = Math.min(this.pixelRatio, step === "ratio15" ? 1.5 : 1);
      this.renderer.setPixelRatio(this.pixelRatio);
      this.resize();
    }
    this.canvas.dataset.quality = step;
  }

  loop(now) {
    if (!this.running) return;
    requestAnimationFrame(this.loop);
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
