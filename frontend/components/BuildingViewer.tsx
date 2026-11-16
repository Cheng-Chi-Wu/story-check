"use client";

import { Edges, Line, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useEffect, useMemo, useState } from "react";
import { STATUS_COLOR, type StoryResult } from "@/lib/types";

// The export has no plan geometry, so the frame is schematic: a 4 x 3 bay grid.
const PLAN_X = 1080; // in
const PLAN_Y = 720; // in
const GRID_X = [-540, -270, 0, 270, 540];
const GRID_Y = [-360, -120, 120, 360];
const SLAB = 10; // in
const S = 0.01; // inches to scene units
const INK = "#14243a";

interface Floor {
  elev: number;
  dx: number;
  dy: number;
  twist: number;
}

/** Cumulative elastic displacement of each floor, from the story drifts. Index 0 is the base. */
function floorsOf(stories: StoryResult[]): Floor[] {
  const floors: Floor[] = [{ elev: 0, dx: 0, dy: 0, twist: 0 }];
  for (const s of stories) {
    const d = s.deformations;
    const below = floors[floors.length - 1];
    floors.push({
      elev: s.elevation_in,
      dx: below.dx + d.avg_drift_x_in,
      dy: below.dy + d.avg_drift_y_in,
      // Edge drift minus average drift, over half the plan depth, is the story twist.
      twist:
        below.twist +
        (d.max_drift_x_in - d.avg_drift_x_in) / (PLAN_Y / 2) +
        (d.max_drift_y_in - d.avg_drift_y_in) / (PLAN_X / 2),
    });
  }
  return floors;
}

function place(px: number, py: number, f: Floor, k: number): [number, number, number] {
  const a = f.twist * k;
  const x = px * Math.cos(a) - py * Math.sin(a) + f.dx * k;
  const z = px * Math.sin(a) + py * Math.cos(a) + f.dy * k;
  return [x * S, f.elev * S, z * S];
}

function Story({
  story,
  below,
  floor,
  k,
  selected,
  onSelect,
}: {
  story: StoryResult;
  below: Floor;
  floor: Floor;
  k: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const color = STATUS_COLOR[story.status];
  const columns = useMemo(() => {
    const pts: [number, number, number][] = [];
    for (const gx of GRID_X) for (const gy of GRID_Y) pts.push(place(gx, gy, below, k), place(gx, gy, floor, k));
    return pts;
  }, [below, floor, k]);

  return (
    <group>
      <Line points={columns} segments color={color} lineWidth={selected ? 3.5 : 1.5} />
      <mesh
        position={place(0, 0, floor, k)}
        rotation={[0, -floor.twist * k, 0]}
        onClick={(e) => {
          e.stopPropagation();
          onSelect();
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "")}
      >
        <boxGeometry args={[PLAN_X * S, SLAB * S, PLAN_Y * S]} />
        <meshStandardMaterial color={color} transparent opacity={selected || story.status !== "PASS" ? 1 : 0.4} />
        {selected && <Edges color={INK} lineWidth={2.5} />}
      </mesh>
    </group>
  );
}

interface Props {
  stories: StoryResult[];
  selected: string | null;
  onSelect: (name: string) => void;
}

export default function BuildingViewer({ stories, selected, onSelect }: Props) {
  const [scale, setScale] = useState(40);
  const [animate, setAnimate] = useState(false);
  const [phase, setPhase] = useState(1);

  useEffect(() => {
    if (!animate) return;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      setPhase(Math.sin(((now - start) / 2500) * 2 * Math.PI));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [animate]);

  const floors = useMemo(() => floorsOf(stories), [stories]);
  const height = floors[floors.length - 1].elev * S;
  const reach = Math.max(height, 12);
  const k = scale * (animate ? phase : 1);

  return (
    <div className="relative h-full min-h-[420px] w-full">
      <Canvas
        key={stories.length}
        camera={{ fov: 32, position: [reach * 1.6 + 10, height * 1.15 + 6, reach * 1.6 + 10], far: 2000 }}
        aria-label="3D model of the building, stories coloured by check result"
      >
        <ambientLight intensity={1.6} />
        <directionalLight position={[40, 80, 30]} intensity={1.4} />
        <gridHelper args={[reach * 3, 24, "#9aa7b5", "#d3dae2"]} />
        {stories.map((s, i) => (
          <Story
            key={s.story_name}
            story={s}
            below={floors[i]}
            floor={floors[i + 1]}
            k={k}
            selected={s.story_name === selected}
            onSelect={() => onSelect(s.story_name)}
          />
        ))}
        <OrbitControls makeDefault target={[0, height / 2, 0]} maxPolarAngle={Math.PI / 2} />
      </Canvas>

      <div className="absolute left-3 top-3 flex flex-col gap-2 border border-line bg-sheet/95 p-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-steel">Deformation scale: {scale}×</span>
          <input
            type="range"
            min={0}
            max={150}
            step={5}
            value={scale}
            onChange={(e) => setScale(Number(e.target.value))}
            className="w-44 accent-[#1d5fbf]"
          />
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={animate} onChange={(e) => setAnimate(e.target.checked)} />
          Animate sway
        </label>
      </div>

      <p className="absolute bottom-3 left-3 max-w-xs bg-paper/90 px-2 py-1 text-xs text-steel">
        Schematic frame. The export has no plan geometry, so bay layout and twist are illustrative; story heights and
        drifts are from your files. Drag to orbit, click a floor to inspect.
      </p>
    </div>
  );
}
