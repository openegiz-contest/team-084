using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Tynys
{
    /// <summary>A close quarry composition of the same twin, with illustrative geometry and transport positions.</summary>
    public sealed class MineCommandView : MonoBehaviour
    {
        public MineWorld world;
        public Transform pitRoot;
        public Transform[] trucks, loads;
        public MeshRenderer[] surfaces, wires;
        public Material[] naturalMaterials;
        public Material digitalSurface;
        public bool Digital { get; private set; }
        public bool SiteView { get; private set; }
        public static readonly Vector3 Origin=new Vector3(260,0,0);
        Material wireMaterial, traceMaterial;

        public void Build()
        {
            pitRoot=new GameObject("COMMAND VIEW · карьер крупным планом").transform;
            pitRoot.SetParent(transform,false);pitRoot.localPosition=Origin;
            var stone=new Material(world.sand){name="Карьер · зернистый камень",color=new Color(.38f,.43f,.47f)};
            stone.mainTexture=RockTexture();stone.SetFloat("_Glossiness",.05f);
            var bench=new Material(world.rock){name="Карьер · пыльная дорога",color=new Color(.64f,.49f,.33f)};
            bench.mainTexture=stone.mainTexture;
            var bottom=new Material(stone){name="Карьер · тёмная порода",color=new Color(.23f,.28f,.32f)};
            var sides=new Material[7];
            for(int i=0;i<7;i++){sides[i]=new Material(world.strata[i]){name="Срез · пласт "+i};sides[i].mainTexture=stone.mainTexture;}
            var terrain=new GameObject("Геологический объём").transform;terrain.SetParent(pitRoot,false);
            terrain.gameObject.AddComponent<MineObject>().Id="pit";
            var v=new List<Vector3>();var t=new List<int>();
            for(int i=0;i<128;i++)
            {
                float a=i*Mathf.PI*2/128,b=(i+1)*Mathf.PI*2/128;
                Quad(v,t,Rim(37.2f,30,a,0),Rim(37.2f,30,b,0),Boundary(b),Boundary(a));
            }
            Mesh("Поверхность",terrain,v,t,stone);
            for(int level=0;level<7;level++)
            {
                v=new List<Vector3>();t=new List<int>();
                float rx=37.2f-level*3.84f,rz=30-level*3f,y=-level*2.3f;
                for(int i=0;i<128;i++)
                {
                    float a=i*Mathf.PI*2/128,b=(i+1)*Mathf.PI*2/128;
                    Quad(v,t,Rim(rx,rz,a,y),Rim(rx-3.84f,rz-3,a,y),Rim(rx-3.84f,rz-3,b,y),Rim(rx,rz,b,y));
                }
                Mesh("Полка уступа "+level,terrain,v,t,bench);
                v=new List<Vector3>();t=new List<int>();
                for(int i=0;i<128;i++)
                {
                    float a=i*Mathf.PI*2/128,b=(i+1)*Mathf.PI*2/128;
                    var upperA=Rim(rx-3.84f,rz-3,a,y);var upperB=Rim(rx-3.84f,rz-3,b,y);
                    Quad(v,t,upperA,Rim(rx-3.84f,rz-3,a,y-2.3f),Rim(rx-3.84f,rz-3,b,y-2.3f),upperB);
                }
                Mesh("Скальный борт "+level,terrain,v,t,sides[level]);
                float depth=22f/7f,sy=-(level+.5f)*depth;
                Cube("Южный пласт",terrain,new Vector3(0,sy,-38),new Vector3(90,depth,.6f),sides[level]);
                Cube("Северный пласт",terrain,new Vector3(0,sy,38),new Vector3(90,depth,.6f),sides[level]);
                Cube("Западный пласт",terrain,new Vector3(-45,sy,0),new Vector3(.6f,depth,76),sides[level]);
                Cube("Восточный пласт",terrain,new Vector3(45,sy,0),new Vector3(.6f,depth,76),sides[level]);
            }
            Cube("Основание",terrain,new Vector3(0,-22.6f,0),new Vector3(91,1.2f,77),world.steel);
            var floor=GameObject.CreatePrimitive(PrimitiveType.Cylinder);floor.name="Дно";floor.transform.SetParent(terrain,false);
            floor.transform.localPosition=new Vector3(0,-16.2f,0);floor.transform.localScale=new Vector3(22,.15f,18);
            floor.GetComponent<MeshRenderer>().sharedMaterial=bottom;
            v=new List<Vector3>();t=new List<int>();
            for(int i=0;i<260;i++)
            {
                float f=i/260f,next=(i+1)/260f;
                var p=Ramp(f);var q=Ramp(next);var side=Vector3.Cross(Vector3.up,(q-p).normalized)*1.55f;
                Quad(v,t,p-side,q-side,q+side,p+side);
            }
            Mesh("Непрерывный съезд",terrain,v,t,bench);
            // A few low-poly blasted rock fragments add scale without importing external models.
            for(int i=0;i<70;i++)
            {
                float a=i*2.39996f,r=40+(i%3)*1.25f;
                var p=new Vector3(Mathf.Cos(a)*r,.12f,Mathf.Sin(a)*r*.8f);
                if(Mathf.Abs(p.x)>43||Mathf.Abs(p.z)>36)continue;
                var rock=Cube("Обломок",terrain,p,new Vector3(.35f+i%4*.22f,.28f+i%3*.14f,.5f),i%2==0?stone:bottom);
                rock.localRotation=Quaternion.Euler(i*13,i*37,i*9);
            }
            foreach(var source in world.GetComponentsInChildren<Transform>())
                if(source.name=="Экскаватор"&&!source.IsChildOf(pitRoot))
                {
                    var clone=Instantiate(source.gameObject,terrain).transform;
                    clone.localPosition=new Vector3((source.position.x+43)*1.2f,source.position.y,source.position.z*1.2f);
                    clone.localRotation=source.rotation;clone.localScale=Vector3.one*.85f;
                }
            trucks=new Transform[14];loads=new Transform[14];
            for(int i=0;i<14;i++)
            {
                trucks[i]=Instantiate(world.trucks[i].gameObject,pitRoot).transform;
                trucks[i].name="Телеметрия · самосвал "+(i+1);trucks[i].localScale=Vector3.one*.82f;
                foreach(var light in trucks[i].GetComponentsInChildren<Light>())DestroyImmediate(light.gameObject);
                loads[i]=trucks[i].Find("Груз");
                // Visible wheel hubs, rear lip and cab visor improve the silhouette at the closer scale.
                Cube("Козырёк",trucks[i],new Vector3(0,2.7f,.6f),new Vector3(3.1f,.15f,2.5f),world.amber);
                Cube("Задний борт",trucks[i],new Vector3(0,2.5f,-2.25f),new Vector3(3,.6f,.17f),world.amber);
                for(int side=-1;side<=1;side+=2)for(int axle=-1;axle<=1;axle+=2)
                {
                    var hub=GameObject.CreatePrimitive(PrimitiveType.Cylinder);hub.name="Ступица";
                    hub.transform.SetParent(trucks[i],false);hub.transform.localPosition=new Vector3(side*1.82f,.8f,axle*1.25f);
                    hub.transform.localRotation=Quaternion.Euler(0,0,90);hub.transform.localScale=new Vector3(.65f,.08f,.65f);
                    hub.GetComponent<MeshRenderer>().sharedMaterial=world.amber;
                }
            }
            wireMaterial=new Material(Shader.Find("Tynys/SurveyLines")){name="Цифровой контур"};
            wireMaterial.color=new Color(.18f,.8f,.95f,.72f);
            traceMaterial=new Material(wireMaterial){name="Траектория · связь",color=new Color(.25f,.9f,.8f,.65f)};
            digitalSurface=new Material(Shader.Find("Standard")){name="Цифровая поверхность",color=new Color(.035f,.12f,.17f)};
            digitalSurface.SetFloat("_Glossiness",.25f);
            var body=new List<MeshRenderer>();foreach(var r in pitRoot.GetComponentsInChildren<MeshRenderer>())body.Add(r);
            surfaces=body.ToArray();naturalMaterials=new Material[surfaces.Length];
            for(int i=0;i<surfaces.Length;i++)naturalMaterials[i]=surfaces[i].sharedMaterial;
            var outlines=new List<MeshRenderer>{WireMesh(terrain,"Геологическая сетка")};
            foreach(var truck in trucks)outlines.Add(WireMesh(truck,"Контур техники"));
            wires=outlines.ToArray();
            foreach(var line in wires)line.enabled=false;
            // Grid and route are presentation overlays, not survey data or extra sensors.
            var gridV=new List<Vector3>();
            for(int x=-60;x<=60;x+=6){gridV.Add(new Vector3(x,-23.5f,-52));gridV.Add(new Vector3(x,-23.5f,52));}
            for(int z=-48;z<=48;z+=6){gridV.Add(new Vector3(-62,-23.5f,z));gridV.Add(new Vector3(62,-23.5f,z));}
            Lines("Координатная сетка · иллюстрация",pitRoot,gridV,new Material(wireMaterial){name="Сетка",color=new Color(.1f,.33f,.42f,.35f)});
            var pathV=new List<Vector3>();
            for(int i=0;i<200;i++){pathV.Add(Ramp(i/200f)+Vector3.up*.12f);pathV.Add(Ramp((i+1)/200f)+Vector3.up*.12f);}
            Lines("Путь транспорта · схема",pitRoot,pathV,traceMaterial);
        }

        static Vector3 Boundary(float a)
        {
            float x=Mathf.Cos(a),z=Mathf.Sin(a),d=Mathf.Min(45/Mathf.Max(.00001f,Mathf.Abs(x)),38/Mathf.Max(.00001f,Mathf.Abs(z)));
            return new Vector3(x*d,0,z*d);
        }
        static Vector3 Rim(float rx,float rz,float a,float y)
        {
            float shape=1+.028f*Mathf.Sin(a*3)+.013f*Mathf.Sin(a*11)+.006f*Mathf.Sin(a*29);
            return new Vector3(Mathf.Cos(a)*rx*shape,y,Mathf.Sin(a)*rz*shape);
        }
        public static Vector3 Ramp(float f)
        {
            float a=f*1.55f*Mathf.PI*2;
            float step=Mathf.Clamp((10.8f+24*f-10.32f)/3.84f,0,6),tier=Mathf.Floor(step);
            float climb=Mathf.SmoothStep(0,1,Mathf.InverseLerp(.58f,1,step-tier));
            float y=-13.8f+(tier+climb)*2.3f+.22f;
            return new Vector3(Mathf.Cos(a)*(10.8f+24*f),y,Mathf.Sin(a)*(8.4f+19.2f*f));
        }
        static void Quad(List<Vector3> v,List<int> t,Vector3 a,Vector3 b,Vector3 c,Vector3 d)
        {
            int n=v.Count;v.AddRange(new[]{a,b,c,d});t.AddRange(new[]{n,n+1,n+2,n,n+2,n+3});
        }
        static MeshRenderer Mesh(string name,Transform parent,List<Vector3> v,List<int> t,Material material)
        {
            var mesh=new Mesh{name=name};mesh.SetVertices(v);mesh.SetTriangles(t,0);
            var uv=new List<Vector2>();foreach(var p in v)uv.Add(new Vector2(p.x*.18f,(p.z+p.y*1.7f)*.18f));
            mesh.SetUVs(0,uv);mesh.RecalculateNormals();mesh.RecalculateBounds();
            var g=new GameObject(name,typeof(MeshFilter),typeof(MeshRenderer));g.transform.SetParent(parent,false);
            g.GetComponent<MeshFilter>().sharedMesh=mesh;g.AddComponent<MeshCollider>().sharedMesh=mesh;
            var r=g.GetComponent<MeshRenderer>();r.sharedMaterial=material;return r;
        }
        static Transform Cube(string name,Transform parent,Vector3 p,Vector3 s,Material material)
        {
            var g=GameObject.CreatePrimitive(PrimitiveType.Cube);g.name=name;g.transform.SetParent(parent,false);
            g.transform.localPosition=p;g.transform.localScale=s;g.GetComponent<MeshRenderer>().sharedMaterial=material;return g.transform;
        }
        static Texture2D RockTexture()
        {
            var texture=new Texture2D(256,256,TextureFormat.RGB24,true){name="Скальная поверхность",wrapMode=TextureWrapMode.Repeat};
            for(int y=0;y<256;y++)for(int x=0;x<256;x++)
            {
                float broad=Mathf.PerlinNoise(x*.035f,y*.035f),fine=Mathf.PerlinNoise(x*.35f,y*.35f);
                float fissure=Mathf.Pow(Mathf.Abs(Mathf.Sin(x*.12f+Mathf.PerlinNoise(x*.04f,y*.05f)*8)),.22f);
                float c=Mathf.Clamp01(.28f+.43f*broad+.22f*fine+.16f*fissure);
                texture.SetPixel(x,y,new Color(c,c*.98f,c*.95f));
            }
            texture.Apply();return texture;
        }
        struct Edge { public Vector3 a,b,normal; public bool crease; }
        MeshRenderer WireMesh(Transform root,string name)
        {
            var vertices=new List<Vector3>();
            foreach(var mf in root.GetComponentsInChildren<MeshFilter>())
            {
                var mesh=mf.sharedMesh;if(mf.name=="Груз"||mesh==null||mesh.GetTopology(0)!=MeshTopology.Triangles)continue;
                var p=mesh.vertices;var tri=mesh.triangles;var edges=new Dictionary<string,Edge>();
                var local=root.worldToLocalMatrix*mf.transform.localToWorldMatrix;
                for(int i=0;i<tri.Length;i+=3)
                {
                    Vector3 normal=Vector3.Cross(p[tri[i+1]]-p[tri[i]],p[tri[i+2]]-p[tri[i]]).normalized;
                    for(int e=0;e<3;e++)
                    {
                        Vector3 a=p[tri[i+e]],b=p[tri[i+(e+1)%3]];
                        string ka=Key(a),kb=Key(b),key=string.CompareOrdinal(ka,kb)<0?ka+"/"+kb:kb+"/"+ka;
                        if(edges.TryGetValue(key,out var edge)){edge.crease=Vector3.Dot(edge.normal,normal)<.93f;edges[key]=edge;}
                        else edges[key]=new Edge{a=a,b=b,normal=normal,crease=true};
                    }
                }
                foreach(var edge in edges.Values)if(edge.crease){vertices.Add(local.MultiplyPoint3x4(edge.a));vertices.Add(local.MultiplyPoint3x4(edge.b));}
            }
            return Lines(name,root,vertices,wireMaterial);
        }
        static string Key(Vector3 p)=>Mathf.RoundToInt(p.x*1000)+","+Mathf.RoundToInt(p.y*1000)+","+Mathf.RoundToInt(p.z*1000);
        static MeshRenderer Lines(string name,Transform parent,List<Vector3> vertices,Material material)
        {
            var g=new GameObject(name,typeof(MeshFilter),typeof(MeshRenderer));g.transform.SetParent(parent,false);
            var mesh=new Mesh{name=name,indexFormat=IndexFormat.UInt32};mesh.SetVertices(vertices);
            var indices=new int[vertices.Count];for(int i=0;i<indices.Length;i++)indices[i]=i;
            mesh.SetIndices(indices,MeshTopology.Lines,0);mesh.RecalculateBounds();
            g.GetComponent<MeshFilter>().sharedMesh=mesh;var r=g.GetComponent<MeshRenderer>();r.sharedMaterial=material;r.shadowCastingMode=ShadowCastingMode.Off;return r;
        }
        void Start(){ShowSite(false);}
        public void ShowSite(bool value)
        {
            SiteView=value;world.cameraRig.SetComposition(value?new Vector3(0,-3,0):Origin+new Vector3(0,-8,0),value?78:56);
        }
        public void SetDigital(bool value)
        {
            Digital=value;
            for(int i=0;i<surfaces.Length;i++)surfaces[i].sharedMaterial=value?digitalSurface:naturalMaterials[i];
            foreach(var wire in wires)wire.enabled=value;
        }
        void LateUpdate()
        {
            if(world==null||world.data==null)return;
            var data=world.data;var s=data.State;
            for(int i=0;i<trucks.Length;i++)
            {
                bool valid=data.HasSnapshot&&s!=null&&s.trucks!=null&&i<s.trucks.Length;
                trucks[i].gameObject.SetActive(valid);if(!valid)continue;
                var state=s.trucks[i];bool travelling=state.state=="loaded"||state.state=="empty";
                if(travelling)
                {
                    float phase=world.TruckVisualPhase(i),f=phase<.5f?phase*2:2-phase*2;
                    var pos=Ramp(f);var tangent=Ramp(Mathf.Clamp01(f+.002f))-Ramp(Mathf.Clamp01(f-.002f));
                    if(phase>=.5f)tangent=-tangent;
                    trucks[i].localPosition=pos+Vector3.Cross(Vector3.up,tangent.normalized)*.65f;
                    if(tangent.sqrMagnitude>.00001f)trucks[i].localRotation=Quaternion.LookRotation(tangent,Vector3.up);
                }
                else{trucks[i].localPosition=new Vector3(-27+(i%7)*8,.2f,33+(i/7)*3);trucks[i].localRotation=Quaternion.Euler(0,90,0);}
                if(loads[i]!=null)loads[i].gameObject.SetActive(state.state=="loaded");
            }
        }
    }
}
