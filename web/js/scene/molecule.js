// the molecule in space. real coordinates, glossy materials, stars, bokeh and a real depth of field

import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { BokehPass } from "three/addons/postprocessing/BokehPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

// drawn radius in angstrom, a bit under the covalent look so the bonds stay visible
const RADII = { H: 0.2, C: 0.44, N: 0.42, O: 0.42, F: 0.38, P: 0.54, S: 0.54, Cl: 0.52, Br: 0.56, I: 0.6 };
const ATOM_TOKENS = { H: "--atom-h", C: "--atom-c", N: "--atom-n", O: "--atom-o", F: "--atom-f", P: "--atom-p",
                      S: "--atom-s", Cl: "--atom-cl", Br: "--atom-br", I: "--atom-i" };
const BOND_RADIUS = 0.07;
const DOUBLE_BOND_GAP = 0.13;

const FOV = 32;
const STAR_COUNT = 260;
const BOKEH_COUNT = 16;
const JEWELS = ["--jewel-pink", "--jewel-amber", "--jewel-ice", "--jewel-plum", "--jewel-cobalt", "--jewel-pearl"];

const SPIN_SPEED = 0.14; // radians a second
const SLOW_FRAME_MS = 26; // a frame slower than this for a while means one quality step down
const FRAMES_PER_CHECK = 45;
const FRICTION = 0.94; // how fast a flick dies down

const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// the same sky on every load
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
  // alpha only, the colour comes from the tokens through the sprite material
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.35, "rgba(255,255,255,0.62)");
  gradient.addColorStop(0.7, "rgba(255,255,255,0.16)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export class MoleculeScene {
  constructor(canvas, { theme = "dark" } = {}) {
    this.canvas = canvas;
    this.theme = theme;
    this.reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
    this.coarse = matchMedia("(pointer: coarse)").matches;
    // ?quality=full switches the automatic quality steps off, for screenshots on a slow machine
    this.fixedQuality = new URLSearchParams(location.search).get("quality") === "full";

    this.active = true;
    this.onScreen = true;
    this.needsFrame = true;
    this.frame = 0;
    this.velocity = 0;
    this.radius = 8;
    this.pixelRatio = Math.min(devicePixelRatio || 1, 2);
    this.qualitySteps = ["transmission", "dof", "bloom", "ratio15", "ratio1"];
    if (this.coarse) this.qualitySteps.shift(); // phones start without transmission
    this.frameMs = [];

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(this.pixelRatio);

    this.scene = new THREE.Scene();
    this.moleculeScene = new THREE.Scene(); // the depth pass only sees the molecule, not the sky
    this.camera = new THREE.PerspectiveCamera(FOV, 1, 1, 500);
    this.group = new THREE.Group();
    this.group.rotation.set(0.25, 0.5, 0);
    this.scene.add(this.group);

    this.buildLights();
    this.buildSky();
    this.buildPipeline();
    this.setTheme(theme);
    this.bindEvents();
    this.resize();
    this.loop = this.loop.bind(this);
    requestAnimationFrame(this.loop);
  }

  buildLights() {
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    // the clearcoat needs something to reflect, without this the gloss has nothing to show
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();
    this.scene.environmentIntensity = 0.7;

    const key = new THREE.DirectionalLight(token("--star"), 2.2);
    key.position.set(4, 8, 10);
    const rimCool = new THREE.DirectionalLight(token("--jewel-ice"), 1.6);
    rimCool.position.set(-8, 3, -4);
    const rimWarm = new THREE.DirectionalLight(token("--jewel-pink"), 1.1);
    rimWarm.position.set(7, -5, -3);
    this.scene.add(key, rimCool, rimWarm);
  }

  buildSky() {
    const random = seededRandom(7);

    // stars far behind the molecule
    const positions = new Float32Array(STAR_COUNT * 3);
    const sizes = new Float32Array(STAR_COUNT);
    for (let i = 0; i < STAR_COUNT; i++) {
      positions.set([(random() - 0.5) * 260, (random() - 0.5) * 260, -60 - random() * 140], i * 3);
      sizes[i] = random();
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    this.stars = new THREE.Points(geometry, new THREE.PointsMaterial({
      color: token("--star"), size: 0.55, sizeAttenuation: true, transparent: true, opacity: 0.85,
      map: softCircleTexture(), depthWrite: false,
    }));
    this.scene.add(this.stars);

    // big soft circles in the jewel colours
    const texture = softCircleTexture();
    this.bokeh = [];
    for (let i = 0; i < BOKEH_COUNT; i++) {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: texture, color: token(JEWELS[i % JEWELS.length]), transparent: true, depthWrite: false,
      }));
      const size = 4 + random() * 11;
      sprite.scale.set(size, size, 1);
      // mostly above the middle, the hero text sits at the bottom
      sprite.position.set((random() - 0.5) * 70, (random() - 0.3) * 60, -24 - random() * 30);
      sprite.userData = { base: sprite.position.y, phase: random() * Math.PI * 2, weight: 0.45 + random() * 0.55 };
      this.bokeh.push(sprite);
      this.scene.add(sprite);
    }
  }

  buildPipeline() {
    const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: this.coarse ? 2 : 4 });
    this.composer = new EffectComposer(this.renderer, target);
    this.composer.addPass(new RenderPass(this.scene, this.camera));

    this.dof = new BokehPass(this.moleculeScene, this.camera, { focus: 40, aperture: 0.0005, maxblur: 0.008 });
    // without this the sky counts as far away and the stars blur to nothing, only the molecule goes soft
    this.dof.materialBokeh.fragmentShader = this.dof.materialBokeh.fragmentShader.replace(
      "float factor = ( focus + viewZ );",
      "float factor = getDepth( vUv ) > 0.9999 ? 0.0 : ( focus + viewZ );",
    );
    this.composer.addPass(this.dof);

    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.22, 0.5, 0.82);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
  }

  setMolecule(mol) {
    this.clearMolecule();

    // hydrogens hidden by default, as in the design
    const shown = new Map();
    mol.atoms.forEach(([element], i) => {
      if (element !== "H") shown.set(i, shown.size);
    });
    const atoms = [...shown.keys()].map((i) => mol.atoms[i]);
    this.radius = Math.max(...atoms.map(([, x, y, z]) => Math.hypot(x, y, z))) + 0.6;

    this.addAtoms(atoms);
    this.addBonds(mol, shown);
    this.mirror = this.group.clone(false);
    this.group.children.forEach((child) => {
      const copy = new THREE.InstancedMesh(child.geometry, child.material, child.count);
      copy.instanceMatrix = child.instanceMatrix;
      this.mirror.add(copy);
    });
    this.moleculeScene.add(this.mirror);
    this.resize();
    this.needsFrame = true;
  }

  clearMolecule() {
    this.group.clear();
    if (this.mirror) this.moleculeScene.remove(this.mirror);
  }

  addAtoms(atoms) {
    const elements = new Map();
    for (const atom of atoms) {
      if (!elements.has(atom[0])) elements.set(atom[0], []);
      elements.get(atom[0]).push(atom);
    }
    const segments = this.coarse ? 20 : 32;
    const sphere = new THREE.SphereGeometry(1, segments, Math.round(segments * 0.75));
    const matrix = new THREE.Matrix4();
    for (const [element, list] of elements) {
      const mesh = new THREE.InstancedMesh(sphere, this.atomMaterial(element), list.length);
      const r = RADII[element] ?? 0.5;
      list.forEach(([, x, y, z], i) => {
        matrix.makeScale(r, r, r).setPosition(x, y, z);
        mesh.setMatrixAt(i, matrix);
      });
      this.group.add(mesh);
    }
  }

  atomMaterial(element) {
    const carbon = element === "C";
    const pearl = element === "N" || element === "H";
    return new THREE.MeshPhysicalMaterial({
      color: token(ATOM_TOKENS[element] ?? "--atom-other"),
      roughness: carbon ? 0.22 : 0.16,
      metalness: carbon ? 0.45 : 0.05, // the little sparkle on the dark carbon
      clearcoat: 1,
      clearcoatRoughness: 0.08,
      // transmission costs a full extra render, so phones skip it
      transmission: pearl && !this.coarse ? 0.25 : 0,
      thickness: pearl ? 0.6 : 0,
      ior: 1.5,
    });
  }

  addBonds(mol, shown) {
    const segments = [];
    const a = new THREE.Vector3();
    const b = new THREE.Vector3();
    const side = new THREE.Vector3();
    const offset = new THREE.Vector3();
    for (const [i, j, order] of mol.bonds) {
      if (!shown.has(i) || !shown.has(j)) continue;
      a.fromArray(mol.atoms[i], 1);
      b.fromArray(mol.atoms[j], 1);
      if (order < 2) {
        segments.push([a.clone(), b.clone()]);
        continue;
      }
      // any direction square to the bond does for the sideways step of a double bond
      side.subVectors(b, a).normalize();
      offset.set(side.y, -side.x, 0);
      if (offset.lengthSq() < 1e-4) offset.set(1, 0, 0);
      offset.normalize().multiplyScalar(DOUBLE_BOND_GAP);
      segments.push([a.clone().add(offset), b.clone().add(offset)], [a.clone().sub(offset), b.clone().sub(offset)]);
    }

    const cylinder = new THREE.CylinderGeometry(BOND_RADIUS, BOND_RADIUS, 1, this.coarse ? 8 : 12);
    const material = new THREE.MeshPhysicalMaterial({
      color: token("--bond"), metalness: 0.9, roughness: 0.28, clearcoat: 0.6,
    });
    const mesh = new THREE.InstancedMesh(cylinder, material, segments.length);
    const up = new THREE.Vector3(0, 1, 0);
    const quaternion = new THREE.Quaternion();
    const middle = new THREE.Vector3();
    const scale = new THREE.Vector3();
    const matrix = new THREE.Matrix4();
    const direction = new THREE.Vector3();
    segments.forEach(([from, to], i) => {
      direction.subVectors(to, from);
      middle.addVectors(from, to).multiplyScalar(0.5);
      quaternion.setFromUnitVectors(up, direction.clone().normalize());
      scale.set(1, direction.length(), 1);
      mesh.setMatrixAt(i, matrix.compose(middle, quaternion, scale));
    });
    this.group.add(mesh);
  }

  setTheme(theme) {
    this.theme = theme;
    const dark = theme === "dark";
    this.scene.background = new THREE.Color(token("--hero"));
    this.scene.environmentIntensity = dark ? 0.7 : 0.42; // on white the pearl atoms need some shading to show
    this.stars.visible = dark;
    this.bloomWanted = dark;
    // neutral keeps the jewels and the page colour exact, on white it would grey the page so it is off there
    this.renderer.toneMapping = dark ? THREE.NeutralToneMapping : THREE.NoToneMapping;
    const opacity = parseFloat(token("--bokeh-opacity"));
    for (const sprite of this.bokeh) {
      sprite.material.opacity = opacity * sprite.userData.weight;
      sprite.material.blending = dark ? THREE.AdditiveBlending : THREE.NormalBlending;
      sprite.material.needsUpdate = true;
    }
    this.applyQuality();
    this.needsFrame = true;
  }

  applyQuality() {
    const off = this.droppedSteps ?? new Set();
    this.dof.enabled = !off.has("dof");
    this.bloom.enabled = this.bloomWanted && !off.has("bloom");
  }

  dropQuality() {
    const step = this.qualitySteps.shift();
    if (!step) return;
    this.droppedSteps = this.droppedSteps ?? new Set();
    this.droppedSteps.add(step);
    if (step === "transmission") {
      this.group.traverse((o) => {
        if (o.material?.transmission) {
          o.material.transmission = 0;
          o.material.needsUpdate = true;
        }
      });
    } else if (step === "ratio15" || step === "ratio1") {
      this.pixelRatio = Math.min(this.pixelRatio, step === "ratio15" ? 1.5 : 1);
      this.renderer.setPixelRatio(this.pixelRatio);
      this.composer.setPixelRatio(this.pixelRatio);
      this.resize();
    }
    this.applyQuality();
  }

  watchSpeed(ms) {
    if (this.fixedQuality || this.frame < 10) return; // the first frames compile shaders, they do not count
    this.frameMs.push(ms);
    if (this.frameMs.length < FRAMES_PER_CHECK) return;
    const average = this.frameMs.reduce((sum, v) => sum + v, 0) / this.frameMs.length;
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
    this.reduceMotion.addEventListener("change", () => { this.needsFrame = true; });

    let lastX = null;
    this.canvas.addEventListener("pointerdown", (e) => {
      lastX = e.clientX;
      this.canvas.setPointerCapture(e.pointerId);
    });
    this.canvas.addEventListener("pointermove", (e) => {
      if (lastX === null) return;
      const dx = e.clientX - lastX;
      lastX = e.clientX;
      this.group.rotation.y += dx * 0.008;
      this.velocity = dx * 0.008;
      this.needsFrame = true;
    });
    const release = () => { lastX = null; };
    this.canvas.addEventListener("pointerup", release);
    this.canvas.addEventListener("pointercancel", release); // the browser took over to scroll
  }

  resize() {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (!width || !height) return;
    this.renderer.setSize(width, height, false);
    this.composer.setPixelRatio(this.pixelRatio);
    this.composer.setSize(width, height);

    // fit the molecule in the space above the hero text and shift the picture up by that much
    const usable = Math.min(width * 0.94, height * 0.6);
    const tan = Math.tan(THREE.MathUtils.degToRad(FOV / 2));
    const distance = this.radius / (tan * (usable / height));
    this.camera.aspect = width / height;
    this.camera.near = Math.max(1, distance * 0.3);
    this.camera.far = distance + 240;
    this.camera.position.set(0, 0, distance);
    this.camera.setViewOffset(width, height, 0, height * 0.09, width, height);
    this.camera.updateProjectionMatrix();

    this.dof.materialBokeh.uniforms.focus.value = distance;
    // the same softness at the back of the molecule, whatever its size
    this.dof.materialBokeh.uniforms.aperture.value = 0.0062 / this.radius;
    this.dof.materialBokeh.uniforms.maxblur.value = 0.0075;
    this.needsFrame = true;
  }

  setActive(active) {
    this.active = active;
    if (active) {
      this.needsFrame = true;
      this.resize(); // the canvas had no size while its view was hidden
    }
  }

  loop(now) {
    requestAnimationFrame(this.loop);
    const elapsed = this.lastNow ? now - this.lastNow : 16;
    this.lastNow = now;
    if (!this.active || !this.onScreen || document.hidden) return;

    const still = this.reduceMotion.matches;
    const moving = Math.abs(this.velocity) > 0.0002;
    if (still && !this.needsFrame && !moving) return; // reduced motion only draws when something changed
    this.needsFrame = false;

    const dt = Math.min(elapsed, 100) / 1000;
    if (!still) {
      this.group.rotation.y += SPIN_SPEED * dt;
      this.group.rotation.x = 0.25 + Math.sin(now / 6000) * 0.08;
      for (const sprite of this.bokeh) {
        sprite.position.y = sprite.userData.base + Math.sin(now / 5000 + sprite.userData.phase) * 0.8;
      }
    }
    if (moving) {
      this.group.rotation.y += this.velocity;
      this.velocity *= FRICTION;
    }
    if (this.mirror) {
      this.mirror.rotation.copy(this.group.rotation);
    }

    this.composer.render(dt);
    this.frame += 1;
    if (!still) this.watchSpeed(elapsed);
  }
}
