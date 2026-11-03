// the molecule in clear tinted glass on a calm background. real coordinates, one canvas for Today and Molecule

import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { BokehPass } from "three/addons/postprocessing/BokehPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

// proportions, as fractions of the molecule's own average bond length
const ATOM_FRACTION = { H: 0.14, C: 0.28, N: 0.27, O: 0.27, F: 0.25, S: 0.3, Cl: 0.3 };
const OTHER_ATOM_FRACTION = 0.3;
const BOND_FRACTION = 0.04;
const DOUBLE_FRACTION = 0.028;
const DOUBLE_GAP_FRACTION = 0.085;
const ATOM_TOKENS = { H: "--atom-h", C: "--atom-c", O: "--atom-o", N: "--atom-n", S: "--atom-s", Cl: "--atom-cl", F: "--atom-f" };

const FOV = 28;
const CROP_RADIUS = 7; // angstrom. on Today a bigger molecule is cropped to this, never shrunk
const BOKEH_COUNT = 7;
const BLUR = 0.009;
const FOCUS_BACK = 0.15; // the focus lies just behind the middle, the far side goes soft
const MODES = {
  hero: { fill: 0.4, widthFill: 0.56, lift: 0.1 },
  full: { fill: 0.44, widthFill: 0.47, lift: 0 }, // the whole molecule, nothing cropped
};
const ZOOM_MIN = 0.6;
const ZOOM_MAX = 3;

const ENTRANCE_S = 2.2;
const SWAY = 0.5; // radians either way. it floats and turns a little, drag is what really spins it
const FRICTION = 0.94; // how fast a flick dies down
const SLOW_FRAME_MS = 26; // a frame slower than this for a while means one quality step down
const CHECK_EVERY_MS = 1500; // by the clock, counting frames would leave a slow phone stuttering for the longest
const MIN_FRAMES_PER_CHECK = 3;

const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const tokenNumber = (name) => parseFloat(token(name));
const color = (name) => new THREE.Color(token(name));

function seededRandom(seed) {
  return () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
}

function softCircleTexture() {
  const size = 128;
  const canvas = Object.assign(document.createElement("canvas"), { width: size, height: size });
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  // alpha only, the colour comes from the tokens through the material
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.5, "rgba(255,255,255,0.7)");
  gradient.addColorStop(0.85, "rgba(255,255,255,0.25)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

// a rigid turn, so the coordinates stay the real ones: longest axis sideways, flattest side to the viewer
function faceTheCamera(atoms) {
  const c = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const { real } of atoms) {
    const p = real.toArray();
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) c[i][j] += p[i] * p[j];
  }
  const axis = (seed, away) => {
    let v = new THREE.Vector3(...seed);
    for (let n = 0; n < 40; n++) {
      const a = v.toArray();
      v = new THREE.Vector3(...c.map((row) => row[0] * a[0] + row[1] * a[1] + row[2] * a[2]));
      for (const other of away) v.addScaledVector(other, -v.dot(other));
      v.normalize();
    }
    return v;
  };
  const x = axis([1, 0.3, 0.2], []);
  const y = axis([0.2, 1, 0.3], [x]);
  const z = new THREE.Vector3().crossVectors(x, y);
  const turn = new THREE.Matrix4().makeBasis(x, y, z).invert();
  atoms.forEach((a) => a.real.applyMatrix4(turn));
}

function busiestRegion(atoms) {
  let best = -1;
  let centre = new THREE.Vector3();
  for (const candidate of atoms) {
    let score = 0;
    for (const a of atoms) {
      if (a.real.distanceTo(candidate.real) < CROP_RADIUS) score += a.element === "C" ? 1 : 2.5; // the chemistry is in the hetero atoms
    }
    if (score > best) {
      best = score;
      centre = candidate.real.clone();
    }
  }
  return centre;
}

function prepare(raw, hydrogens) {
  const keep = new Map();
  raw.atoms.forEach((a, i) => { if (hydrogens || a[0] !== "H") keep.set(i, keep.size); });
  const atoms = [...keep.keys()].map((i) => ({
    element: raw.atoms[i][0], real: new THREE.Vector3(raw.atoms[i][1], raw.atoms[i][2], raw.atoms[i][3]), now: new THREE.Vector3(),
  }));
  const bonds = raw.bonds.filter(([i, j]) => keep.has(i) && keep.has(j))
    .map(([i, j, order]) => ({ i: keep.get(i), j: keep.get(j), order }));
  const heavy = bonds.filter((b) => atoms[b.i].element !== "H" && atoms[b.j].element !== "H");
  const unit = heavy.reduce((sum, b) => sum + atoms[b.i].real.distanceTo(atoms[b.j].real), 0) / (heavy.length || 1);
  faceTheCamera(atoms);

  const radiusAll = Math.max(...atoms.map((a) => a.real.length())) + unit * 0.3;
  const crop = radiusAll > CROP_RADIUS ? busiestRegion(atoms.filter((a) => a.element !== "H")) : new THREE.Vector3();
  const random = seededRandom(raw.name.length * 97 + 3);
  atoms.forEach((a) => {
    const direction = new THREE.Vector3(random() - 0.5, random() - 0.5, random() - 0.5).normalize();
    a.cloud = direction.multiplyScalar(Math.min(radiusAll, CROP_RADIUS) * (1.4 + random() * 1.6));
    a.delay = random() * 0.35;
  });
  return { atoms, bonds, unit, radiusAll, crop };
}

export class MoleculeScene {
  constructor(canvas, { theme = "dark" } = {}) {
    this.canvas = canvas;
    this.theme = theme;
    this.reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
    this.coarse = matchMedia("(pointer: coarse)").matches;
    const params = new URLSearchParams(location.search);
    // ?quality=full and ?entrance=0 are for screenshots on a slow machine
    this.fixedQuality = params.get("quality") === "full";
    this.skipEntrance = params.get("entrance") === "0";

    this.mode = "hero";
    this.hydrogens = false;
    this.zoom = 1;
    this.active = true;
    this.onScreen = true;
    this.needsFrame = true;
    this.paused = this.reduceMotion.matches;
    this.raw = null;
    this.mol = null;
    this.velocity = 0;
    this.dragAngle = 0;
    this.dragTilt = 0;
    this.swayClock = 0;
    this.parallax = { x: 0, y: 0, tx: 0, ty: 0, touched: -Infinity };
    this.entrance = { active: false, start: 0, p: 1 };
    this.uParallax = { value: 0 };
    this.frame = 0;
    this.pixelRatio = Math.min(devicePixelRatio || 1, 2);
    this.qualitySteps = ["transmission half", "dof", "fake glass", "ratio15", "ratio1"];
    this.droppedSteps = new Set();
    this.frameMs = [];
    this.soft = softCircleTexture();

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(this.pixelRatio);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(FOV, 1, 1, 600);
    [this.pivot, this.group] = this.nestedGroups(this.scene);
    this.pivot.rotation.set(0.2, 0, -0.12);
    // depth of field only looks at the molecule, not at the sky
    this.depthScene = new THREE.Scene();
    [this.depthPivot, this.depthGroup] = this.nestedGroups(this.depthScene);
    this.sky = new THREE.Group();
    this.scene.add(this.sky);

    // lamps close to the molecule, not at infinity: each atom sees them from its own angle
    this.key = new THREE.PointLight(color("--strip-main"), 1, 0, 0);
    this.warm = new THREE.PointLight(color("--strip-warm"), 1, 0, 0);
    this.scene.add(this.key, this.warm);

    this.buildPipeline();
    this.setTheme(theme);
    this.bindEvents();
    this.loop = this.loop.bind(this);
    requestAnimationFrame(this.loop);
  }

  nestedGroups(parent) {
    const outer = new THREE.Group();
    const inner = new THREE.Group();
    outer.add(inner);
    parent.add(outer);
    return [outer, inner];
  }

  buildPipeline() {
    const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: this.coarse ? 2 : 4 });
    this.composer = new EffectComposer(this.renderer, target);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.dof = new BokehPass(this.depthScene, this.camera, { focus: 40, aperture: 0.001, maxblur: BLUR });
    // only what lies behind the focus goes soft. the sky has no depth of its own, so it borrows the blur
    // of what lies next to it, otherwise a soft atom gets a hard outline
    this.dof.materialBokeh.fragmentShader = this.dof.materialBokeh.fragmentShader.replace(
      "float factor = ( focus + viewZ );",
      `float rawDepth = getDepth( vUv );
       float factor = min( 0.0, focus + viewZ );
       if ( rawDepth > 0.9999 ) {
         factor = 0.0;
         for ( int k = 0; k < 8; k++ ) {
           float a = float( k ) * 0.7854;
           vec2 probe = vUv + vec2( cos( a ), sin( a ) * aspect ) * maxblur * 0.4;
           float d = getDepth( probe );
           if ( d <= 0.9999 ) factor = min( factor, min( 0.0, focus + getViewZ( d ) ) );
         }
       }`,
    );
    this.composer.addPass(this.dof);
    this.composer.addPass(new OutputPass());
  }

  // a dark room with strips of light, all the glass has to reflect
  buildStudio() {
    const room = new THREE.Scene();
    room.add(new THREE.Mesh(new THREE.SphereGeometry(50, 32, 16),
      new THREE.MeshBasicMaterial({ color: color("--studio-room"), side: THREE.BackSide })));
    const strip = (name, power, x, y, z, w, h) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h),
        new THREE.MeshBasicMaterial({ color: color(name).multiplyScalar(power), side: THREE.DoubleSide }));
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

  // a calm vertical gradient that ends in the page colour, a few soft lights far behind
  buildSky() {
    const canvas = Object.assign(document.createElement("canvas"), { width: 4, height: 256 });
    const ctx = canvas.getContext("2d");
    const gradient = ctx.createLinearGradient(0, 0, 0, 256);
    gradient.addColorStop(0, token("--sky-top"));
    gradient.addColorStop(0.5, token("--sky-middle"));
    gradient.addColorStop(1, token("--hero"));
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 4, 256);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;

    this.sky.clear();
    const random = seededRandom(11);
    for (let i = 0; i < BOKEH_COUNT; i++) {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: this.soft, color: color(i % 3 === 2 ? "--bokeh-b" : "--bokeh-a"), transparent: true, depthWrite: false,
        opacity: tokenNumber("--bokeh-opacity") * (0.5 + random() * 0.5),
      }));
      const size = 5 + random() * 11;
      sprite.scale.set(size, size, 1);
      sprite.position.set((random() - 0.5) * 50, (random() - 0.3) * 36, -24 - random() * 30);
      this.sky.add(sprite);
    }
    return texture;
  }

  setMolecule(raw) {
    this.raw = raw;
    this.mol = prepare(raw, this.hydrogens);
    this.applyMode();
    this.buildMolecule();
    this.placeAtoms(0);
    this.playEntrance();
    this.needsFrame = true;
  }

  setHydrogens(show) {
    this.hydrogens = show;
    if (!this.raw) return;
    this.mol = prepare(this.raw, show);
    this.applyMode();
    this.buildMolecule();
    this.needsFrame = true;
  }

  // Today frames the busy part, the Molecule screen shows all of it, the coordinates stay the real ones
  setMode(mode) {
    this.mode = mode;
    this.zoom = 1;
    this.dragTilt = 0;
    this.applyMode();
    if (this.mol?.tubes && !this.entrance.active) this.placeAtoms(1);
    this.needsFrame = true;
  }

  applyMode() {
    const mol = this.mol;
    if (mol) {
      const offset = this.mode === "hero" ? mol.crop : new THREE.Vector3();
      mol.atoms.forEach((a) => { a.home = a.real.clone().sub(offset); });
      mol.frameRadius = this.mode === "hero" ? Math.min(mol.radiusAll, CROP_RADIUS) : mol.radiusAll;
    }
    this.canvas.style.touchAction = this.mode === "hero" ? "pan-y" : "none";
    this.resize();
  }

  buildMolecule() {
    const mol = this.mol;
    if (!mol) return;
    for (const group of [this.group, this.depthGroup]) group.clear();
    const segments = this.coarse ? 32 : 48;
    const sphere = new THREE.SphereGeometry(1, segments, Math.round(segments * 0.7));
    const instanced = (geometry, material, count) => {
      const mesh = new THREE.InstancedMesh(geometry, material, count);
      mesh.frustumCulled = false;
      this.group.add(mesh);
      const copy = new THREE.InstancedMesh(geometry, new THREE.MeshBasicMaterial(), count);
      copy.instanceMatrix = mesh.instanceMatrix;
      copy.frustumCulled = false;
      this.depthGroup.add(copy);
      return mesh;
    };
    const byElement = new Map();
    mol.atoms.forEach((a, i) => {
      if (!byElement.has(a.element)) byElement.set(a.element, []);
      byElement.get(a.element).push(i);
    });
    for (const [element, list] of byElement) {
      const mesh = instanced(sphere, this.glass(element), list.length);
      const r = (ATOM_FRACTION[element] ?? OTHER_ATOM_FRACTION) * mol.unit;
      list.forEach((atomIndex, slot) => Object.assign(mol.atoms[atomIndex], { mesh, slot, r }));
    }

    // a double bond is two thin tubes next to each other
    mol.tubes = [];
    for (const b of mol.bonds) {
      if (b.order < 2) {
        mol.tubes.push({ from: b.i, to: b.j, side: 0, radius: BOND_FRACTION * mol.unit });
      } else {
        mol.tubes.push({ from: b.i, to: b.j, side: 1, radius: DOUBLE_FRACTION * mol.unit });
        mol.tubes.push({ from: b.i, to: b.j, side: -1, radius: DOUBLE_FRACTION * mol.unit });
      }
    }
    const tube = new THREE.CylinderGeometry(1, 1, 1, this.coarse ? 8 : 12);
    mol.tubeMesh = instanced(tube, new THREE.MeshPhysicalMaterial({
      color: color("--bond"), metalness: 0.6, roughness: 0.22, clearcoat: 0.6, envMapIntensity: 1.2,
    }), mol.tubes.length);
    this.placeAtoms(this.entrance.active ? this.entrance.p : 1);
    this.applyQuality();
  }

  glass(element) {
    const tint = color(ATOM_TOKENS[element] ?? "--atom-cl");
    const white = color("--strip-main");
    const material = new THREE.MeshPhysicalMaterial({
      color: tint.clone().lerp(white, 0.6), roughness: 0.04, metalness: 0, transmission: 1, thickness: 0.8, ior: 1.5,
      attenuationColor: tint, attenuationDistance: 0.9,
      emissive: tint, emissiveIntensity: tokenNumber("--glass-glow"), // on a dark page glass only shows what it reflects, this gives it a body
      iridescence: 0.25, iridescenceIOR: 1.3, iridescenceThicknessRange: [180, 420],
      envMapIntensity: this.theme === "dark" ? 1.8 : 1.1,
    });
    // a sphere in a far away studio reflects the same picture wherever it stands, so every atom looks in from its own spot
    material.onBeforeCompile = (shader) => {
      shader.uniforms.uParallax = this.uParallax;
      shader.vertexShader = `varying vec3 vAtomWorld;\n${shader.vertexShader}`.replace(
        "#include <project_vertex>",
        "#include <project_vertex>\n vAtomWorld = (modelMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;",
      );
      // this line belongs to three.js and can change with a new version, so a miss has to be loud
      const line = "reflectVec = transformDirectionByInverseViewMatrix( reflectVec, viewMatrix );";
      const chunk = THREE.ShaderChunk.envmap_physical_pars_fragment;
      if (!chunk.includes(line)) console.warn("three.js changed its reflection shader, every atom reflects the same again");
      shader.fragmentShader = `uniform float uParallax; varying vec3 vAtomWorld;\n${shader.fragmentShader}`.replace(
        "#include <envmap_physical_pars_fragment>",
        chunk.replace(line, `${line}\n reflectVec = normalize( reflectVec + vAtomWorld * uParallax );`),
      );
    };
    return material;
  }

  // positions at entrance progress p. p = 1 is exactly the real structure
  placeAtoms(p) {
    const mol = this.mol;
    const matrix = new THREE.Matrix4();
    for (const a of mol.atoms) {
      const local = THREE.MathUtils.clamp((p - a.delay) / (1 - a.delay), 0, 1);
      const eased = 1 - (1 - local) ** 4;
      a.now.copy(a.cloud).lerp(a.home, eased);
      const r = a.r * (0.22 + 0.78 * eased);
      a.mesh.setMatrixAt(a.slot, matrix.makeScale(r, r, r).setPosition(a.now));
      a.mesh.instanceMatrix.needsUpdate = true;
    }
    const grow = THREE.MathUtils.smoothstep(p, 0.72, 1); // the bonds only grow once the atoms are nearly home
    const direction = new THREE.Vector3();
    const offset = new THREE.Vector3();
    const middle = new THREE.Vector3();
    const size = new THREE.Vector3();
    const turn = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    mol.tubes.forEach((t, i) => {
      const from = mol.atoms[t.from].now;
      const to = mol.atoms[t.to].now;
      direction.subVectors(to, from);
      const length = direction.length();
      direction.normalize();
      turn.setFromUnitVectors(up, direction);
      offset.set(0, 0, 0);
      if (t.side) {
        offset.set(direction.y, -direction.x, 0);
        if (offset.lengthSq() < 1e-4) offset.set(1, 0, 0);
        offset.normalize().multiplyScalar(t.side * DOUBLE_GAP_FRACTION * mol.unit);
      }
      middle.addVectors(from, to).multiplyScalar(0.5).add(offset);
      size.set(t.radius * grow + 1e-4, length, t.radius * grow + 1e-4);
      mol.tubeMesh.setMatrixAt(i, matrix.compose(middle, turn, size));
    });
    mol.tubeMesh.instanceMatrix.needsUpdate = true;
  }

  playEntrance() {
    if (this.reduceMotion.matches || this.skipEntrance) {
      Object.assign(this.entrance, { active: false, p: 1 });
      this.placeAtoms(1);
      return;
    }
    Object.assign(this.entrance, { active: true, start: performance.now(), p: 0 });
  }

  setTheme(theme) {
    this.theme = theme;
    this.scene.background?.dispose();
    this.scene.environment?.dispose();
    this.scene.background = this.buildSky();
    this.scene.environment = this.buildStudio();
    this.key.intensity = tokenNumber("--light-key");
    this.warm.intensity = tokenNumber("--light-warm");
    this.warm.color = color("--strip-warm");
    // neutral keeps the page colour exact on navy, on white it would grey the page so it is off there
    this.renderer.toneMapping = theme === "dark" ? THREE.NeutralToneMapping : THREE.NoToneMapping;
    this.resize();
    this.buildMolecule();
    this.needsFrame = true;
  }

  setPaused(paused) {
    this.paused = paused;
    this.velocity = 0;
    this.needsFrame = true;
  }

  applyQuality() {
    const off = this.droppedSteps;
    this.dof.enabled = !off.has("dof");
    this.renderer.transmissionResolutionScale = off.has("transmission half") ? 0.5 : 1;
    if (off.has("fake glass")) {
      // no render of the background behind every atom any more, plain see through is far cheaper
      this.group.traverse((o) => {
        if (o.material?.transmission) {
          o.material.transmission = 0;
          o.material.transparent = true;
          o.material.opacity = 0.7;
          o.material.needsUpdate = true;
        }
      });
    }
  }

  dropQuality() {
    const step = this.qualitySteps.shift();
    if (!step) return;
    this.droppedSteps.add(step);
    if (step === "ratio15" || step === "ratio1") {
      this.pixelRatio = Math.min(this.pixelRatio, step === "ratio15" ? 1.5 : 1);
      this.renderer.setPixelRatio(this.pixelRatio);
      this.composer.setPixelRatio(this.pixelRatio);
      this.resize();
    }
    this.applyQuality();
    this.canvas.dataset.quality = [...this.droppedSteps].join(", ");
  }

  watchSpeed(ms) {
    if (this.fixedQuality || this.frame < 4) return; // the first frames compile shaders, they do not count
    this.frameMs.push(ms);
    const total = this.frameMs.reduce((sum, v) => sum + v, 0);
    if (total < CHECK_EVERY_MS || this.frameMs.length < MIN_FRAMES_PER_CHECK) return;
    const average = total / this.frameMs.length;
    this.frameMs.length = 0;
    if (average > SLOW_FRAME_MS) this.dropQuality();
  }

  bindEvents() {
    new ResizeObserver(() => this.resize()).observe(this.canvas);
    // no point drawing what nobody sees
    new IntersectionObserver(([entry]) => {
      this.onScreen = entry.isIntersecting;
      if (this.onScreen) this.needsFrame = true;
    }).observe(this.canvas);
    document.addEventListener("visibilitychange", () => { this.needsFrame = true; });

    const pointers = new Map();
    let pinch = null;
    const spread = () => {
      const [a, b] = [...pointers.values()];
      return Math.hypot(a.x - b.x, a.y - b.y);
    };
    this.canvas.addEventListener("pointerdown", (e) => {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      this.canvas.setPointerCapture(e.pointerId);
      if (pointers.size === 2 && this.mode === "full") pinch = { distance: spread(), zoom: this.zoom };
    });
    this.canvas.addEventListener("pointermove", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.parallax.tx = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
      this.parallax.ty = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
      this.parallax.touched = performance.now();
      const last = pointers.get(e.pointerId);
      if (!last) return;
      const dx = e.clientX - last.x;
      const dy = e.clientY - last.y;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pinch && pointers.size === 2) {
        this.setZoom(pinch.zoom * (spread() / pinch.distance));
        return;
      }
      this.dragAngle += dx * 0.008;
      this.velocity = dx * 0.008;
      if (this.mode === "full") this.dragTilt = THREE.MathUtils.clamp(this.dragTilt + dy * 0.008, -1.4, 1.4);
      this.needsFrame = true;
    });
    const release = (e) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
    };
    this.canvas.addEventListener("pointerup", release);
    this.canvas.addEventListener("pointercancel", release); // the browser took over to scroll
    this.canvas.addEventListener("wheel", (e) => {
      if (this.mode !== "full") return;
      e.preventDefault();
      this.setZoom(this.zoom * Math.exp(-e.deltaY * 0.001));
    }, { passive: false });
    // the arrow keys and plus and minus do what drag and pinch do
    this.canvas.addEventListener("keydown", (e) => {
      const turns = { ArrowLeft: [-0.15, 0], ArrowRight: [0.15, 0], ArrowUp: [0, -0.15], ArrowDown: [0, 0.15] }[e.key];
      if (turns) {
        e.preventDefault();
        this.dragAngle += turns[0];
        this.dragTilt = THREE.MathUtils.clamp(this.dragTilt + turns[1], -1.4, 1.4);
        this.needsFrame = true;
      } else if (e.key === "+" || e.key === "=") this.setZoom(this.zoom * 1.15);
      else if (e.key === "-") this.setZoom(this.zoom / 1.15);
    });
    addEventListener("deviceorientation", (e) => {
      if (e.gamma === null) return; // tilting the phone moves the view, where the browser allows it
      this.parallax.tx = THREE.MathUtils.clamp(e.gamma / 25, -1, 1);
      this.parallax.ty = THREE.MathUtils.clamp((e.beta - 45) / 25, -1, 1);
      this.parallax.touched = performance.now();
    });
  }

  setZoom(zoom) {
    this.zoom = THREE.MathUtils.clamp(zoom, ZOOM_MIN, ZOOM_MAX);
    this.resize();
  }

  resize() {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (!width || !height) return;
    this.renderer.setSize(width, height, false);
    this.composer.setPixelRatio(this.pixelRatio);
    this.composer.setSize(width, height);

    const mode = MODES[this.mode];
    const radius = this.mol?.frameRadius ?? CROP_RADIUS;
    const radiusAll = this.mol?.radiusAll ?? CROP_RADIUS;
    // the same on-screen size for every molecule
    const fillPx = Math.min(width * mode.widthFill, height * mode.fill) * this.zoom;
    const tan = Math.tan(THREE.MathUtils.degToRad(FOV / 2));
    const distance = radius / (tan * (fillPx / (height / 2)));
    this.camera.aspect = width / height;
    this.camera.near = Math.max(0.5, distance - radiusAll * 2.2);
    this.camera.far = distance + 300;
    this.camera.userData.distance = distance;
    this.camera.setViewOffset(width, height, 0, height * mode.lift, width, height);
    this.camera.updateProjectionMatrix();

    this.key.position.set(-0.7 * radius, 1 * radius, 1.3 * radius);
    this.warm.position.set(1.2 * radius, -0.6 * radius, 0.8 * radius);
    this.uParallax.value = 0.7 / radius; // an atom at the edge of the frame sees a clearly different reflection

    const blur = BLUR * (this.theme === "light" ? 0.6 : 1); // soft atoms wash out on white
    const uniforms = this.dof.materialBokeh.uniforms;
    uniforms.focus.value = distance + radius * FOCUS_BACK;
    uniforms.aperture.value = blur / (radius * (1 - FOCUS_BACK * 0.8));
    uniforms.maxblur.value = blur;
    this.needsFrame = true;
  }

  setActive(active) {
    this.active = active;
    if (active) {
      this.resize(); // the canvas had no size while its view was hidden
      this.needsFrame = true;
    }
  }

  loop(now) {
    requestAnimationFrame(this.loop);
    const elapsed = this.lastNow ? now - this.lastNow : 16;
    this.lastNow = now;
    if (!this.active || !this.onScreen || document.hidden) return;

    const moving = Math.abs(this.velocity) > 0.0002;
    if (this.paused && !this.needsFrame && !moving && !this.entrance.active) return; // paused only draws when something changed
    this.needsFrame = false;

    const dt = Math.min(elapsed, 100) / 1000;
    const t = now / 1000;
    const mol = this.mol;

    if (mol && this.entrance.active) {
      this.entrance.p = Math.min((now - this.entrance.start) / (ENTRANCE_S * 1000), 1);
      this.placeAtoms(this.entrance.p);
      if (this.entrance.p >= 1) this.entrance.active = false;
    }
    if (!this.paused && mol) {
      this.swayClock += dt;
      this.pivot.position.y = Math.sin(t * 0.7) * mol.frameRadius * 0.025;
      this.pivot.rotation.z = -0.12 + Math.sin(t * 0.5) * 0.02;
      // gentle parallax. without a pointer or a tilt it sways on its own
      const p = this.parallax;
      if (now - p.touched > 3000) {
        p.tx = Math.sin(t * 0.23) * 0.6;
        p.ty = Math.cos(t * 0.17) * 0.4;
      }
      p.x += (p.tx - p.x) * 0.04;
      p.y += (p.ty - p.y) * 0.04;
    }
    this.dragAngle += this.velocity;
    this.velocity *= FRICTION;
    this.group.rotation.y = this.dragAngle + Math.sin(this.swayClock * 0.3) * SWAY;
    this.pivot.rotation.x = 0.2 + this.dragTilt;
    this.depthGroup.rotation.copy(this.group.rotation);
    this.depthPivot.rotation.copy(this.pivot.rotation);
    this.depthPivot.position.copy(this.pivot.position);

    const size = mol?.frameRadius ?? CROP_RADIUS;
    this.camera.position.set(this.parallax.x * size * 0.16, -this.parallax.y * size * 0.1, this.camera.userData.distance ?? 40);
    this.camera.lookAt(0, 0, 0);

    this.composer.render(dt);
    this.frame += 1;
    if (!this.paused) this.watchSpeed(elapsed);
  }
}
