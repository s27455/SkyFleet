import { ContactShadows, Environment, Lightformer, OrbitControls } from '@react-three/drei'
import { Canvas, useThree } from '@react-three/fiber'
import { useEffect, useRef, type ComponentRef, type RefObject } from 'react'
import type { PerspectiveCamera } from 'three'

import {
  CAMERA_LIMITS,
  CAMERA_TARGET,
  DEFAULT_CAMERA_POSITION,
  fitZoom,
  orbitPosition,
  zoomPosition,
  type Vec3,
} from './cameraMath'
import { DroneModel } from './DroneModel'
import { SKID_Y } from './droneLayout'
import type { DronePartId } from './droneParts'

/** Camera commands the viewer's keyboard and buttons use; filled in once the scene is mounted. */
export interface CameraApi {
  orbit(deltaAzimuth: number, deltaPolar: number): void
  zoom(factor: number): void
  reset(): void
}

export interface DroneCanvasProps {
  /** True only while propellers should spin: drives `frameloop="always"`; otherwise render on demand. */
  running: boolean
  /** Mouse-wheel zoom is enabled only while the viewer has focus so it never hijacks page scroll. */
  wheelZoom: boolean
  apiRef: RefObject<CameraApi | null>
  onPartSelect?: (part: DronePartId) => void
  onContextLost?: () => void
}

type Controls = ComponentRef<typeof OrbitControls>

function CameraRig({
  apiRef,
  controls,
}: {
  apiRef: RefObject<CameraApi | null>
  controls: RefObject<Controls | null>
}) {
  const camera = useThree((state) => state.camera) as PerspectiveCamera
  const size = useThree((state) => state.size)
  const invalidate = useThree((state) => state.invalidate)

  // Narrow viewports zoom the projection out so the whole drone stays in view.
  useEffect(() => {
    // Three.js cameras are mutable by design; React Three Fiber expects direct mutation here.
    // oxlint-disable-next-line react/immutability
    camera.zoom = fitZoom(size.width / Math.max(size.height, 1))
    camera.updateProjectionMatrix()
    invalidate()
  }, [camera, size.width, size.height, invalidate])

  useEffect(() => {
    const place = (position: Vec3) => {
      camera.position.set(...position)
      controls.current?.update()
      invalidate()
    }
    const current = (): Vec3 => [camera.position.x, camera.position.y, camera.position.z]
    apiRef.current = {
      orbit: (azimuth, polar) => place(orbitPosition(current(), CAMERA_TARGET, azimuth, polar)),
      zoom: (factor) => place(zoomPosition(current(), CAMERA_TARGET, factor)),
      reset: () => place(DEFAULT_CAMERA_POSITION),
    }
    return () => {
      apiRef.current = null
    }
  }, [apiRef, camera, controls, invalidate])

  return null
}

export default function DroneCanvas({
  running,
  wheelZoom,
  apiRef,
  onPartSelect,
  onContextLost,
}: DroneCanvasProps) {
  const controls = useRef<Controls>(null)

  return (
    <Canvas
      className="touch-none"
      frameloop={running ? 'always' : 'demand'}
      dpr={[1, 2]}
      camera={{ position: [...DEFAULT_CAMERA_POSITION], fov: 38, near: 0.1, far: 40 }}
      onCreated={({ gl }) => {
        gl.domElement.addEventListener('webglcontextlost', (event) => {
          event.preventDefault()
          onContextLost?.()
        })
      }}
    >
      {/* Procedural studio reflections: no downloaded HDRI, rendered once. */}
      <Environment resolution={256} frames={1}>
        <Lightformer form="rect" intensity={2.4} position={[0, 5, 3]} scale={[9, 3, 1]} />
        <Lightformer
          form="rect"
          intensity={1.3}
          color="#9fd8e8"
          position={[-5, 1, -2]}
          rotation-y={Math.PI / 2}
          scale={[6, 2, 1]}
        />
        <Lightformer
          form="rect"
          intensity={0.9}
          position={[5, 0.5, 2]}
          rotation-y={-Math.PI / 2}
          scale={[5, 2, 1]}
        />
        <Lightformer form="ring" intensity={1.6} position={[0, 3, -5]} scale={4} />
      </Environment>
      <directionalLight position={[3, 5, 4]} intensity={1.1} />
      <ambientLight intensity={0.12} />

      <DroneModel spinning={running} onPartSelect={onPartSelect} />
      <ContactShadows
        position={[0, SKID_Y - 0.05, 0]}
        opacity={0.5}
        scale={6}
        blur={2.6}
        far={1.6}
        resolution={512}
        frames={1}
      />

      <OrbitControls
        ref={controls}
        target={[...CAMERA_TARGET]}
        enablePan={false}
        enableZoom={wheelZoom}
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.7}
        zoomSpeed={0.6}
        minDistance={CAMERA_LIMITS.minDistance}
        maxDistance={CAMERA_LIMITS.maxDistance}
        minPolarAngle={CAMERA_LIMITS.minPolar}
        maxPolarAngle={CAMERA_LIMITS.maxPolar}
      />
      <CameraRig apiRef={apiRef} controls={controls} />
    </Canvas>
  )
}
