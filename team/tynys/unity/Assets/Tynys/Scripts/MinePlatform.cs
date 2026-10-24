using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Rendering.PostProcessing;

namespace Tynys
{
    /// <summary>Portable font, restrained browser rendering and read-only browser diagnostics.</summary>
    public sealed class MinePlatform : MonoBehaviour
    {
        static Font uiFont;
        public static bool AllowTruckLights => Application.platform != RuntimePlatform.WebGLPlayer;
        // IMGUI tints are linear in this project's rendering pipeline; keep authored UI hex colours exact.
        public static Color GuiColor(Color color) => QualitySettings.activeColorSpace==ColorSpace.Linear?color.linear:color;
        public static Font UiFont => uiFont != null ? uiFont :
            (uiFont = Resources.Load<Font>("Fonts/DejaVuSans") ?? Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf"));

        [Serializable]
        class BrowserStatus
        {
            public string mode, status;
            public string presentation;
            public bool connected, stale, hasSnapshot, softwareRenderer;
            public int snapshotCount, frameCount, renderedFrameCount, batchedObjects;
            public float hour;
        }
        MineData data;
        float nextStatus;
        bool softwareRenderer;
        int renderedFrameCount, batchedObjects;
#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] static extern void TynysStatus(string json);
        [DllImport("__Internal")] static extern int TynysSoftwareRenderer();
#endif
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Install()
        {
            new GameObject("Tynys platform profile").AddComponent<MinePlatform>();
        }
        void Start()
        {
            data = FindFirstObjectByType<MineData>();
#if UNITY_WEBGL && !UNITY_EDITOR
            // OS fonts are unavailable in browsers; the licensed Cyrillic font is embedded.
            WebGLInput.captureAllKeyboardInput = false;
            softwareRenderer = TynysSoftwareRenderer() != 0;
            Application.targetFrameRate = softwareRenderer ? 15 : 30;
            QualitySettings.pixelLightCount = 1;
            QualitySettings.shadowResolution = ShadowResolution.Medium;
            QualitySettings.shadowDistance = 150;
            QualitySettings.antiAliasing = 0; // FXAA remains active.
            foreach (var light in FindObjectsByType<Light>(FindObjectsSortMode.None))
                if (light.type == LightType.Spot) light.enabled = false; // Emissive lenses remain visible.
            foreach (var volume in FindObjectsByType<PostProcessVolume>(FindObjectsSortMode.None))
            {
                var profile = volume.profile;
                if (profile.TryGetSettings(out AmbientOcclusion ao)) ao.enabled.Override(false);
                if (profile.TryGetSettings(out Bloom bloom)) { bloom.fastMode.Override(true); bloom.diffusion.Override(4); }
            }
            if (softwareRenderer)
            {
                QualitySettings.shadows = ShadowQuality.Disable;
                foreach (var layer in FindObjectsByType<PostProcessLayer>(FindObjectsSortMode.None)) layer.enabled = false;
                foreach (var camera in FindObjectsByType<Camera>(FindObjectsSortMode.None)) { camera.allowHDR = false; camera.allowMSAA = false; }
                foreach (var particle in FindObjectsByType<ParticleSystemRenderer>(FindObjectsSortMode.None)) particle.enabled = false;
                foreach (var probe in FindObjectsByType<ReflectionProbe>(FindObjectsSortMode.None)) probe.enabled = false;
            }
            BatchStationaryGeometry();
            StartCoroutine(CountRenderedFrames());
#endif
        }
        IEnumerator CountRenderedFrames()
        {
            var endOfFrame = new WaitForEndOfFrame();
            while (true) { yield return endOfFrame; renderedFrameCount++; }
        }
        void BatchStationaryGeometry()
        {
            var world = FindFirstObjectByType<MineWorld>();
            if (world == null) return;
            var animated = new List<Transform>();
            animated.AddRange(world.trucks); animated.AddRange(world.rotors); animated.AddRange(world.mills);
            animated.AddRange(world.stockpiles); animated.AddRange(world.flowDots);
            var command=world.GetComponent<MineCommandView>();
            if(command!=null&&command.trucks!=null)animated.AddRange(command.trucks);
            foreach (var bar in world.batteryBars) animated.Add(bar.transform);
            foreach (var status in world.lineStatus) animated.Add(status.transform);
            var stationary = new List<GameObject>();
            foreach (var renderer in world.GetComponentsInChildren<MeshRenderer>())
            {
                var mesh = renderer.GetComponent<MeshFilter>();
                if (mesh == null || mesh.sharedMesh == null || !mesh.sharedMesh.isReadable || renderer.GetComponent<TextMesh>() != null) continue;
                if (renderer.sharedMaterial == null || renderer.sharedMaterial.renderQueue >= 3000) continue;
                bool moves = false;
                foreach (var root in animated) if (root != null && renderer.transform.IsChildOf(root)) { moves = true; break; }
                if (!moves) stationary.Add(renderer.gameObject);
            }
            if (stationary.Count == 0) return;
            StaticBatchingUtility.Combine(stationary.ToArray(), world.gameObject);
            batchedObjects = stationary.Count;
        }
        void Update()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            if (data == null || Time.realtimeSinceStartup < nextStatus) return;
            nextStatus = Time.realtimeSinceStartup + 1;
            TynysStatus(JsonUtility.ToJson(new BrowserStatus {
                mode = data.LiveMode ? "LIVE" : "DEMO", status = data.Status,
                presentation = PresentationName(),
                connected = data.IsConnected, stale = data.IsStale, hasSnapshot = data.HasSnapshot,
                snapshotCount = data.SnapshotCount, frameCount = Time.frameCount, renderedFrameCount = renderedFrameCount,
                softwareRenderer = softwareRenderer, batchedObjects = batchedObjects,
                hour = data.HasSnapshot ? data.State.hour : -1
            }));
#endif
        }
        string PresentationName()
        {
            var command=GetCommand();
            return command==null||command.SiteView?"site":command.Digital?"digital":"pit";
        }
        MineCommandView GetCommand()=>data==null?null:data.GetComponent<MineCommandView>();
    }
}
