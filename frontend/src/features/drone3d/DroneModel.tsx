import { RoundedBox } from '@react-three/drei'
import { useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  BackSide,
  CapsuleGeometry,
  CircleGeometry,
  CylinderGeometry,
  ExtrudeGeometry,
  LatheGeometry,
  Quaternion,
  Shape,
  SphereGeometry,
  SplineCurve,
  TorusGeometry,
  Vector2,
  Vector3,
  type Group,
} from 'three'

import {
  FUSELAGE_HALF_LENGTH,
  MOTOR_LAYOUT,
  PROPELLER_LIFT,
  PROPELLER_RADIUS,
  SKID_Y,
  type MotorLayout,
} from './droneLayout'
import {
  createDroneMaterials,
  disposeMaterials,
  highlightFor,
  ledFor,
  type DroneMaterials,
} from './droneMaterials'
import { propellerName, type DronePartId, type PartAnnotation } from './droneParts'

const PROPELLER_SPEED = 9 // rad/s: clearly spinning, but calm enough not to strobe
const Y_AXIS = new Vector3(0, 1, 0)

function createGeometries() {
  // Fuselage: a smooth, tapered body of revolution along its length (axis Y, rotated to Z later).
  const profile = new SplineCurve(
    [
      [0, -0.99],
      [0.17, -0.95],
      [0.34, -0.82],
      [0.43, -0.6],
      [0.46, -0.2],
      [0.46, 0.3],
      [0.42, 0.65],
      [0.3, 0.88],
      [0.12, 0.97],
      [0, 0.99],
    ].map(([radius, y]) => new Vector2(radius, y)),
  ).getPoints(48)

  // Propeller blade: a tapered leaf with a rounded tip, laid flat in the XZ plane.
  const reach = PROPELLER_RADIUS
  const leaf = new Shape()
  leaf.moveTo(0.06, -0.03)
  leaf.bezierCurveTo(0.2, -0.09, 0.45, -0.08, reach * 0.96, -0.035)
  leaf.quadraticCurveTo(reach, 0, reach * 0.96, 0.035)
  leaf.bezierCurveTo(0.45, 0.04, 0.2, 0.05, 0.06, 0.03)
  leaf.closePath()
  const blade = new ExtrudeGeometry(leaf, { depth: 0.012, bevelEnabled: false, curveSegments: 16 })
  blade.translate(0, 0, -0.006)
  blade.rotateX(-Math.PI / 2)

  const disc = new CircleGeometry(reach, 48)
  disc.rotateX(-Math.PI / 2)

  return {
    fuselage: new LatheGeometry(profile, 56),
    blade,
    disc,
    skid: new CapsuleGeometry(0.03, 1.5, 6, 16),
    sensorDome: new SphereGeometry(0.11, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2),
    antenna: new CylinderGeometry(0.008, 0.012, 0.34, 8),
    motorHousing: new CylinderGeometry(0.15, 0.17, 0.2, 40),
    motorBell: new CylinderGeometry(0.135, 0.15, 0.05, 40),
    motorMount: new CylinderGeometry(0.2, 0.2, 0.03, 32),
    motorRing: new TorusGeometry(0.168, 0.011, 8, 48),
    // Health ring around a motor and the selection outline around its propeller (rotated flat on use).
    haloRing: new TorusGeometry(0.3, 0.024, 10, 64),
    selectRing: new TorusGeometry(PROPELLER_RADIUS + 0.1, 0.02, 8, 72),
    hub: new CylinderGeometry(0.035, 0.075, 0.07, 24),
    post: new CylinderGeometry(0.024, 0.024, 0.4, 12),
  }
}
type Geometries = ReturnType<typeof createGeometries>

/** Creates the geometries once and disposes every one on unmount (StrictMode safe). */
function useGeometries(): Geometries {
  const geometries = useMemo(() => createGeometries(), [])
  useEffect(
    () => () => {
      for (const geometry of Object.values(geometries)) geometry.dispose()
    },
    [geometries],
  )
  return geometries
}

function useMaterials(): DroneMaterials {
  const materials = useMemo(() => createDroneMaterials(), [])
  useEffect(() => () => disposeMaterials(materials), [materials])
  return materials
}

type Point = readonly [number, number, number]

/** A straight, tapered strut between two points (arms, landing legs). */
function Strut({
  from,
  to,
  radiusFrom,
  radiusTo,
  material,
}: {
  from: Point
  to: Point
  radiusFrom: number
  radiusTo: number
  material: DroneMaterials['carbon']
}) {
  const [fx, fy, fz] = from
  const [tx, ty, tz] = to
  const { position, quaternion, length } = useMemo(() => {
    const a = new Vector3(fx, fy, fz)
    const b = new Vector3(tx, ty, tz)
    const direction = b.clone().sub(a)
    return {
      length: direction.length(),
      position: a.clone().add(b).multiplyScalar(0.5),
      quaternion: new Quaternion().setFromUnitVectors(Y_AXIS, direction.normalize()),
    }
  }, [fx, fy, fz, tx, ty, tz])
  // The cylinder's top (+Y) is the `to` end.
  const geometry = useMemo(
    () => new CylinderGeometry(radiusTo, radiusFrom, length, 20),
    [radiusFrom, radiusTo, length],
  )
  useEffect(() => () => geometry.dispose(), [geometry])
  return (
    <mesh geometry={geometry} material={material} position={position} quaternion={quaternion} />
  )
}

interface PartHandlers {
  onClick?: (event: ThreeEvent<MouseEvent>) => void
  onPointerOver?: (event: ThreeEvent<PointerEvent>) => void
  onPointerOut?: (event: ThreeEvent<PointerEvent>) => void
}

function Motor({
  layout,
  geometries,
  materials,
  spinning,
  handlers,
  annotation,
  outlined,
}: {
  layout: MotorLayout
  geometries: Geometries
  materials: DroneMaterials
  spinning: boolean
  handlers: PartHandlers
  annotation?: PartAnnotation
  /** Drawn with the selection outline (selected or hovered). */
  outlined: boolean
}) {
  const highlight = annotation ? highlightFor(materials, annotation.level) : null
  const propeller = useRef<Group>(null)
  useFrame((_, delta) => {
    if (spinning && propeller.current) {
      // Clamp so a stalled tab does not produce a huge jump when frames resume.
      propeller.current.rotation.y += layout.spin * PROPELLER_SPEED * Math.min(delta, 0.05)
    }
  })

  return (
    <group
      name={layout.id}
      userData={{ partId: layout.id }}
      position={[...layout.position]}
      {...handlers}
    >
      <mesh geometry={geometries.motorMount} material={materials.carbon} position={[0, -0.04, 0]} />
      <mesh
        geometry={geometries.motorHousing}
        material={materials.motorMetal}
        position={[0, 0.06, 0]}
      />
      <mesh
        geometry={geometries.motorRing}
        material={
          highlight && annotation ? ledFor(materials, annotation.level) : materials.ledAccent
        }
        position={[0, -0.02, 0]}
        rotation={[Math.PI / 2, 0, 0]}
      />
      {highlight && (
        <>
          <mesh
            geometry={geometries.haloRing}
            material={highlight.ring}
            position={[0, 0.06, 0]}
            rotation={[Math.PI / 2, 0, 0]}
          />
          <mesh
            geometry={geometries.disc}
            material={highlight.wash}
            position={[0, PROPELLER_LIFT + 0.02, 0]}
          />
        </>
      )}
      {outlined && (
        <mesh
          geometry={geometries.selectRing}
          material={materials.selection}
          position={[0, PROPELLER_LIFT + 0.02, 0]}
          rotation={[Math.PI / 2, 0, 0]}
        />
      )}
      <mesh geometry={geometries.motorBell} material={materials.metal} position={[0, 0.185, 0]} />
      <group
        name={propellerName(layout.id)}
        ref={propeller}
        position={[0, PROPELLER_LIFT + 0.04, 0]}
      >
        <mesh geometry={geometries.hub} material={materials.metal} position={[0, 0.02, 0]} />
        {[0, Math.PI].map((yaw) => (
          <mesh
            key={yaw}
            geometry={geometries.blade}
            material={materials.blade}
            rotation={[0.22, yaw, 0]}
            position={[0, 0.005, 0]}
          />
        ))}
        <mesh geometry={geometries.disc} material={materials.disc} visible={spinning} />
      </group>
    </group>
  )
}

export interface DroneModelProps {
  /** Spin the propellers and add a gentle hover. */
  spinning?: boolean
  /**
   * When set, clicking a part reports it, and clicking empty space reports `null`. Without
   * `annotations` every part is clickable; with them, only the annotated parts are.
   */
  onPartSelect?: (part: DronePartId | null) => void
  /** Health level and label per part: drawn as highlights and labels on the model. */
  annotations?: Readonly<Partial<Record<DronePartId, PartAnnotation>>>
  /** The selected part, drawn with an outline. */
  selectedPart?: DronePartId | null
}

const LEG_SPAN = 0.5

/** Procedural quadcopter built from named groups; geometry and materials are built once. */
export function DroneModel({
  spinning = false,
  onPartSelect,
  annotations,
  selectedPart = null,
}: DroneModelProps) {
  const geometries = useGeometries()
  const materials = useMaterials()
  const hover = useRef<Group>(null)
  const gl = useThree((state) => state.gl)
  const [hovered, setHovered] = useState<DronePartId | null>(null)

  // Leave the canvas cursor as found if the model unmounts while a part is hovered.
  useEffect(
    () => () => {
      gl.domElement.style.cursor = ''
    },
    [gl],
  )

  useFrame(({ clock }) => {
    if (hover.current) {
      hover.current.position.y = spinning ? Math.sin(clock.elapsedTime * 1.4) * 0.018 : 0
    }
  })

  const handlersFor = (part: DronePartId): PartHandlers =>
    onPartSelect && (!annotations || part in annotations)
      ? {
          onClick: (event) => {
            // A drag that orbits the camera also ends in a click: it is not a selection.
            if (event.delta > 4) return
            event.stopPropagation()
            onPartSelect(part)
          },
          onPointerOver: (event) => {
            event.stopPropagation()
            setHovered(part)
            gl.domElement.style.cursor = 'pointer'
          },
          onPointerOut: () => {
            setHovered((current) => (current === part ? null : current))
            gl.domElement.style.cursor = ''
          },
        }
      : {}
  const outlined = (part: DronePartId) =>
    annotations !== undefined && (selectedPart === part || hovered === part)
  const batteryAnnotation = annotations?.battery
  const batteryHighlight = batteryAnnotation
    ? highlightFor(materials, batteryAnnotation.level)
    : null

  return (
    <group ref={hover} name="drone">
      {/* Fuselage: smooth body, nose to +Z, flattened vertically. */}
      <group name="fuselage" userData={{ partId: 'fuselage' }} {...handlersFor('fuselage')}>
        <mesh
          geometry={geometries.fuselage}
          material={materials.shell}
          rotation={[Math.PI / 2, 0, 0]}
          scale={[1, 1, 0.62]}
        />
        {/* Nose: accent light bar and a downward sensor dome. */}
        <RoundedBox
          args={[0.34, 0.025, 0.04]}
          radius={0.01}
          position={[0, 0.02, FUSELAGE_HALF_LENGTH - 0.08]}
          material={materials.ledAccent}
        />
        <mesh
          geometry={geometries.sensorDome}
          material={materials.sensor}
          position={[0, -0.2, 0.68]}
          rotation={[Math.PI, 0, 0]}
        />
        {/* Roof: carbon spine plate and rear antennas. */}
        <RoundedBox
          args={[0.2, 0.02, 0.5]}
          radius={0.01}
          position={[0, 0.285, 0.5]}
          material={materials.carbon}
        />
        {[-0.14, 0.14].map((x) => (
          <mesh
            key={x}
            geometry={geometries.antenna}
            material={materials.carbon}
            position={[x, 0.3, -0.72]}
            rotation={[-0.35, 0, x * 1.2]}
          />
        ))}
      </group>

      {/* Battery: removable pack on the roof, rear. */}
      <group
        name="battery"
        userData={{ partId: 'battery' }}
        position={[0, 0.34, -0.22]}
        {...handlersFor('battery')}
      >
        <RoundedBox
          args={[0.5, 0.17, 0.72]}
          radius={0.05}
          smoothness={4}
          material={materials.graphite}
        />
        <RoundedBox
          args={[0.3, 0.02, 0.5]}
          radius={0.01}
          position={[0, 0.09, 0]}
          material={materials.carbon}
        />
        {[-1, 1].map((sx) => (
          <RoundedBox
            key={sx}
            args={[0.02, 0.05, 0.34]}
            radius={0.008}
            position={[sx * 0.255, 0, 0]}
            material={
              batteryAnnotation ? ledFor(materials, batteryAnnotation.level) : materials.ledOk
            }
          />
        ))}
        {batteryHighlight && (
          <RoundedBox
            args={[0.57, 0.22, 0.79]}
            radius={0.06}
            smoothness={4}
            material={batteryHighlight.wash}
          />
        )}
        {outlined('battery') && (
          <RoundedBox args={[0.6, 0.25, 0.82]} radius={0.07} smoothness={4}>
            <meshBasicMaterial color="#22d3ee" side={BackSide} toneMapped={false} />
          </RoundedBox>
        )}
        <RoundedBox
          args={[0.14, 0.04, 0.03]}
          radius={0.01}
          position={[0, 0, 0.37]}
          material={materials.metal}
        />
      </group>

      {/* Cargo bay: open frame under the body with glass side panels and a parcel inside. */}
      <group name="cargo-bay" userData={{ partId: 'cargo-bay' }} {...handlersFor('cargo-bay')}>
        <RoundedBox
          args={[0.8, 0.045, 1.06]}
          radius={0.02}
          position={[0, -0.69, 0]}
          material={materials.graphite}
        />
        {[-1, 1].flatMap((sx) =>
          [-1, 1].map((sz) => (
            <mesh
              key={`${sx}${sz}`}
              geometry={geometries.post}
              material={materials.carbon}
              position={[sx * 0.38, -0.49, sz * 0.5]}
            />
          )),
        )}
        {[-1, 1].map((sx) => (
          <mesh
            key={sx}
            material={materials.glass}
            position={[sx * 0.385, -0.49, 0]}
            rotation={[0, Math.PI / 2, 0]}
          >
            <planeGeometry args={[0.96, 0.34]} />
          </mesh>
        ))}
        <RoundedBox
          args={[0.56, 0.32, 0.72]}
          radius={0.025}
          smoothness={3}
          position={[0, -0.5, 0]}
          material={materials.parcel}
        />
        <RoundedBox
          args={[0.1, 0.325, 0.725]}
          radius={0.005}
          position={[0, -0.5, 0]}
          material={materials.tape}
        />
      </group>

      {/* Landing gear: four angled legs and two skids. */}
      <group
        name="landing-gear"
        userData={{ partId: 'landing-gear' }}
        {...handlersFor('landing-gear')}
      >
        {[-1, 1].map((sx) => (
          <group key={sx}>
            <mesh
              geometry={geometries.skid}
              material={materials.rubber}
              position={[sx * 0.64, SKID_Y, 0]}
              rotation={[Math.PI / 2, 0, 0]}
            />
            {[-1, 1].map((sz) => (
              <Strut
                key={sz}
                from={[sx * 0.64, SKID_Y, sz * LEG_SPAN]}
                to={[sx * 0.36, -0.1, sz * LEG_SPAN]}
                radiusFrom={0.026}
                radiusTo={0.034}
                material={materials.carbon}
              />
            ))}
          </group>
        ))}
      </group>

      {/* Arms and motors. */}
      <group name="arms">
        {MOTOR_LAYOUT.map((layout) => (
          <Strut
            key={layout.id}
            from={[
              Math.sign(layout.position[0]) * 0.18,
              0.02,
              Math.sign(layout.position[2]) * 0.18,
            ]}
            to={[layout.position[0], 0.02, layout.position[2]]}
            radiusFrom={0.07}
            radiusTo={0.045}
            material={materials.carbon}
          />
        ))}
      </group>
      {MOTOR_LAYOUT.map((layout) => (
        <Motor
          key={layout.id}
          layout={layout}
          geometries={geometries}
          materials={materials}
          spinning={spinning}
          handlers={handlersFor(layout.id)}
          annotation={annotations?.[layout.id]}
          outlined={outlined(layout.id)}
        />
      ))}
    </group>
  )
}
