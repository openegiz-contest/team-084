using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.PostProcessing;

namespace Tynys.Editor
{
    public static class TynysBuilder
    {
        public const string ScenePath="Assets/Tynys/Scenes/TynysMine.unity";

        [MenuItem("Tynys/Build editable mine scene")]
        public static void CreateScene()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            Directory.CreateDirectory("Assets/Tynys/Generated");
            Directory.CreateDirectory("Assets/Tynys/Scenes");
            AssetDatabase.Refresh();
            var root=new GameObject("TYNYS · Digital Mine");
            var data=root.AddComponent<MineData>();
            data.LiveMode=true;
            var world=root.AddComponent<MineWorld>();
            var hud=root.AddComponent<MineHUD>();
            var camera=new GameObject("Обзорная камера",typeof(Camera),typeof(AudioListener),typeof(MineCamera));
            camera.tag="MainCamera";
            var cam=camera.GetComponent<Camera>();
            cam.clearFlags=CameraClearFlags.SolidColor;
            cam.backgroundColor=new Color(.025f,.045f,.065f);
            cam.orthographic=true;cam.orthographicSize=55;cam.farClipPlane=500;cam.nearClipPlane=.1f;
            cam.allowHDR=true;cam.allowMSAA=true;
            camera.transform.position=new Vector3(0,108,-112);
            camera.transform.LookAt(new Vector3(0,-3,0));
            var rig=camera.GetComponent<MineCamera>();
            world.data=data;world.hud=hud;world.viewCamera=cam;world.cameraRig=rig;
            hud.data=data;hud.cameraRig=rig;
            world.Build();
            var command=root.AddComponent<MineCommandView>();command.world=world;command.Build();hud.command=command;
            var sun=new GameObject("Солнце · мягкие тени",typeof(Light));
            sun.transform.rotation=Quaternion.Euler(52,-28,0);
            var light=sun.GetComponent<Light>();light.type=LightType.Directional;light.color=new Color(1,.94f,.82f);
            light.intensity=1.05f;light.shadows=LightShadows.Soft;light.shadowStrength=.58f;light.shadowBias=.03f;
            RenderSettings.sun=light;
            RenderSettings.ambientMode=AmbientMode.Trilight;
            RenderSettings.ambientSkyColor=new Color(.68f,.77f,.83f);
            RenderSettings.ambientEquatorColor=new Color(.51f,.59f,.64f);
            RenderSettings.ambientGroundColor=new Color(.4f,.36f,.31f);
            var sky=new Material(Shader.Find("Skybox/Procedural")){name="Тыныс · светлое дневное небо"};
            sky.SetFloat("_SunSize",.025f);sky.SetFloat("_AtmosphereThickness",.8f);sky.SetFloat("_Exposure",1.1f);
            sky.SetColor("_SkyTint",new Color(.6f,.72f,.82f));sky.SetColor("_GroundColor",new Color(.55f,.58f,.55f));
            AssetDatabase.CreateAsset(sky,"Assets/Tynys/Generated/DaylightSky.mat");RenderSettings.skybox=sky;
            RenderSettings.fog=true;RenderSettings.fogMode=FogMode.Linear;RenderSettings.fogColor=new Color(.09f,.14f,.19f);
            RenderSettings.fogStartDistance=210f;RenderSettings.fogEndDistance=420f;
            RenderSettings.reflectionIntensity=.7f;DynamicGI.UpdateEnvironment();
            var reflection=new GameObject("Дневные отражения",typeof(ReflectionProbe));reflection.transform.position=new Vector3(0,12,0);
            var probe=reflection.GetComponent<ReflectionProbe>();probe.size=new Vector3(220,80,150);probe.mode=ReflectionProbeMode.Realtime;
            probe.refreshMode=ReflectionProbeRefreshMode.OnAwake;probe.timeSlicingMode=ReflectionProbeTimeSlicingMode.AllFacesAtOnce;probe.resolution=128;
            ConfigurePostProcessing(cam);
            QualitySettings.antiAliasing=4;QualitySettings.shadowDistance=250;
            QualitySettings.shadows=ShadowQuality.All;QualitySettings.shadowResolution=ShadowResolution.High;
            QualitySettings.vSyncCount=1;
            PlayerSettings.productName="Тыныс · Актогай";
            PlayerSettings.companyName="Tynys";
            PlayerSettings.defaultScreenWidth=1600;PlayerSettings.defaultScreenHeight=900;
            PlayerSettings.fullScreenMode=FullScreenMode.Windowed;
            PlayerSettings.resizableWindow=true;PlayerSettings.runInBackground=true;
            PlayerSettings.colorSpace=ColorSpace.Linear;
            PlayerSettings.allowUnsafeCode=false;
            PlayerSettings.insecureHttpOption=InsecureHttpOption.AlwaysAllowed;
            EditorUserBuildSettings.development=false;EditorUserBuildSettings.allowDebugging=false;
            // Legacy Input keeps mouse and keyboard controls independent of the input-system package.
            var settings=new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset")[0]);
            var input=settings.FindProperty("activeInputHandler");
            if(input!=null){input.intValue=0;settings.ApplyModifiedPropertiesWithoutUndo();}
            SaveGeneratedAssets(root);
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(),ScenePath);
            EditorBuildSettings.scenes=new[]{new EditorBuildSettingsScene(ScenePath,true)};
            AssetDatabase.SaveAssets();
            Debug.Log("TYNYS_SCENE_OK "+ScenePath);
        }

        static void ConfigurePostProcessing(Camera camera)
        {
            var resources=AssetDatabase.FindAssets("t:PostProcessResources");
            if(resources.Length==0)throw new Exception("Post Processing resources not imported");
            var layer=camera.gameObject.AddComponent<PostProcessLayer>();
            layer.Init(AssetDatabase.LoadAssetAtPath<PostProcessResources>(AssetDatabase.GUIDToAssetPath(resources[0])));
            layer.volumeLayer=1;layer.volumeTrigger=camera.transform;
            layer.antialiasingMode=PostProcessLayer.Antialiasing.FastApproximateAntialiasing;
            var volume=new GameObject("Тыныс · Bloom / AO / Color grading",typeof(PostProcessVolume)).GetComponent<PostProcessVolume>();
            volume.isGlobal=true;volume.priority=1;volume.weight=1;
            var profile=ScriptableObject.CreateInstance<PostProcessProfile>();profile.name="Tynys Daylight";
            var bloom=profile.AddSettings<Bloom>();bloom.enabled.Override(true);bloom.intensity.Override(.65f);
            bloom.threshold.Override(1.15f);bloom.softKnee.Override(.65f);bloom.diffusion.Override(5f);
            var ao=profile.AddSettings<AmbientOcclusion>();ao.enabled.Override(true);
            ao.mode.Override(AmbientOcclusionMode.ScalableAmbientObscurance);ao.intensity.Override(.48f);ao.radius.Override(.65f);
            ao.quality.Override(AmbientOcclusionQuality.Medium);
            var grade=profile.AddSettings<ColorGrading>();grade.enabled.Override(true);
            grade.gradingMode.Override(GradingMode.HighDefinitionRange);grade.tonemapper.Override(Tonemapper.Neutral);
            grade.postExposure.Override(.3f);grade.contrast.Override(7);grade.saturation.Override(5);
            AssetDatabase.CreateAsset(profile,"Assets/Tynys/Generated/DaylightPostProcess.asset");
            foreach(var setting in profile.settings)AssetDatabase.AddObjectToAsset(setting,profile);
            volume.sharedProfile=profile;
        }

        static void SaveGeneratedAssets(GameObject root)
        {
            var seen=new HashSet<UnityEngine.Object>();int index=0,textureIndex=0;
            foreach(var r in root.GetComponentsInChildren<Renderer>())
                foreach(var m in r.sharedMaterials)
                    if(m!=null&&seen.Add(m)&&string.IsNullOrEmpty(AssetDatabase.GetAssetPath(m)))
                    {
                        foreach(var property in m.GetTexturePropertyNames())
                        {
                            var texture=m.GetTexture(property);
                            if(texture!=null&&seen.Add(texture)&&string.IsNullOrEmpty(AssetDatabase.GetAssetPath(texture)))
                                AssetDatabase.CreateAsset(texture,"Assets/Tynys/Generated/Texture_"+(textureIndex++)+".asset");
                        }
                        AssetDatabase.CreateAsset(m,"Assets/Tynys/Generated/Material_"+(index++)+".mat");
                    }
            index=0;
            foreach(var f in root.GetComponentsInChildren<MeshFilter>())
            {
                var mesh=f.sharedMesh;
                if(mesh!=null&&seen.Add(mesh)&&string.IsNullOrEmpty(AssetDatabase.GetAssetPath(mesh)))
                    AssetDatabase.CreateAsset(mesh,"Assets/Tynys/Generated/Mesh_"+(index++)+".asset");
            }
        }

        [MenuItem("Tynys/Build Windows LIVE")]
        public static void BuildWindows()
        {
            if(!File.Exists(ScenePath))CreateScene();
            string path=Environment.GetEnvironmentVariable("TYNYS_BUILD_PATH");
            if(string.IsNullOrEmpty(path))path="Builds/Windows/Tynys.exe";
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions{
                scenes=new[]{ScenePath},locationPathName=path,target=BuildTarget.StandaloneWindows64,
                options=BuildOptions.None});
            if(report.summary.result!=BuildResult.Succeeded)
                throw new Exception("Windows build failed: "+report.summary.result);
            Debug.Log("TYNYS_BUILD_OK "+path);
        }

        public static void CreateAndBuild()
        {
            CreateScene();
            ValidateScene();
            BuildWindows();
        }

        [MenuItem("Tynys/Build Web LIVE")]
        public static void CreateAndBuildWeb()
        {
            CreateScene();
            ValidateScene();
            PlayerSettings.WebGL.compressionFormat=WebGLCompressionFormat.Disabled;
            PlayerSettings.WebGL.decompressionFallback=false;
            PlayerSettings.WebGL.nameFilesAsHashes=false;
            PlayerSettings.WebGL.template="PROJECT:Tynys";
            PlayerSettings.WebGL.threadsSupport=false;
            PlayerSettings.SetManagedStrippingLevel(UnityEditor.Build.NamedBuildTarget.WebGL,ManagedStrippingLevel.Low);
            EditorUserBuildSettings.development=false;
            EditorUserBuildSettings.allowDebugging=false;
            // Stable basename regardless of the external delivery folder.
            string staging="Builds/Tynys";
            Directory.CreateDirectory(staging);
            var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions {
                scenes=new[]{ScenePath},locationPathName=staging,target=BuildTarget.WebGL,options=BuildOptions.None
            });
            if(report.summary.result!=BuildResult.Succeeded)
                throw new Exception("Web build failed: "+report.summary.result);
            File.Copy("Assets/Resources/Fonts/DejaVu-LICENSE.txt",Path.Combine(staging,"DejaVu-LICENSE.txt"),true);
            string output=Environment.GetEnvironmentVariable("TYNYS_WEB_BUILD_PATH");
            if(!string.IsNullOrEmpty(output))CopyTree(staging,output);
            Debug.Log("TYNYS_WEB_BUILD_OK "+(string.IsNullOrEmpty(output)?staging:output));
        }

        static void CopyTree(string source,string destination)
        {
            Directory.CreateDirectory(destination);
            foreach(var file in Directory.GetFiles(source))File.Copy(file,Path.Combine(destination,Path.GetFileName(file)),true);
            foreach(var directory in Directory.GetDirectories(source))CopyTree(directory,Path.Combine(destination,Path.GetFileName(directory)));
        }

        [MenuItem("Tynys/Validate scene")]
        public static void ValidateScene()
        {
            var world=UnityEngine.Object.FindFirstObjectByType<MineWorld>();
            if(world==null)throw new Exception("MineWorld missing");
            if(world.trucks.Length!=14||world.rotors.Length!=6||world.stockpiles.Length!=2||world.mills.Length!=2)
                throw new Exception("Unexpected scene object counts");
            if(world.data==null||world.hud==null||world.cameraRig==null)throw new Exception("Missing scene binding");
            foreach(var t in world.trucks)if(t==null)throw new Exception("Missing truck");
            foreach(var f in world.GetComponentsInChildren<MeshFilter>())
                if(f.sharedMesh==null)throw new Exception("Missing persisted mesh: "+f.name);
            if(world.GetComponentsInChildren<MineObject>().Length<30)throw new Exception("Missing selection IDs");
            if(world.steam.Length!=2||world.truckHeadlights.Length!=28)throw new Exception("Missing particle or headlight bindings");
            var command=UnityEngine.Object.FindFirstObjectByType<MineCommandView>();
            if(command==null||command.trucks.Length!=14||command.wires.Length!=15)throw new Exception("Missing command-view transport or digital layer");
            if(RenderSettings.skybox==null||!RenderSettings.fog)throw new Exception("Missing daylight environment");
            if(world.viewCamera.GetComponent<PostProcessLayer>()==null)throw new Exception("Missing post processing");
            if(PlayerSettings.insecureHttpOption!=InsecureHttpOption.AlwaysAllowed)throw new Exception("Release local HTTP is disabled");
            Debug.Log("TYNYS_VALIDATE_OK · 14 truck groups, 6 turbines, 2 stockpiles, 2 lines");
        }

        [MenuItem("Tynys/Render scene preview")]
        public static void RenderPreview()
        {
            EditorSceneManager.OpenScene(ScenePath);
            var camera=Camera.main;
            camera.rect=new Rect(0,0,1,1);camera.orthographicSize=68;
            camera.transform.position=new Vector3(20,105,-130);camera.transform.LookAt(new Vector3(0,-1,0));
            var rt=new RenderTexture(1920,1080,24);
            camera.targetTexture=rt;camera.Render();
            RenderTexture.active=rt;
            var texture=new Texture2D(1920,1080,TextureFormat.RGB24,false);
            texture.ReadPixels(new Rect(0,0,1920,1080),0,0);texture.Apply();
            Directory.CreateDirectory("Builds");
            File.WriteAllBytes("Builds/Tynys-Scene.png",texture.EncodeToPNG());
            camera.targetTexture=null;RenderTexture.active=null;
            UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(texture);
            Debug.Log("TYNYS_PREVIEW_OK");
        }
    }
}
