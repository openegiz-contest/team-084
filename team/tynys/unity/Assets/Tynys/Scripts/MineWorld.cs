using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Tynys
{
    /// <summary>
    /// An editable, schematic diorama. Positions are illustrative, not survey coordinates.
    /// Geometry is generated in the editor and saved in the scene; runtime only animates it.
    /// </summary>
    public class MineWorld : MonoBehaviour
    {
        public MineData data;
        public Camera viewCamera;
        public MineHUD hud;
        public MineCamera cameraRig;
        public Transform[] rotors, trucks, truckLoads, mills, stockpiles;
        public Renderer[] lineStatus, batteryBars;
        public LineRenderer[] energyFlows, oreFlows;
        public Transform[] flowDots;
        public ParticleSystem[] steam;
        public Light[] truckHeadlights;
        public Vector3[] route;
        public int outboundCount=10;
        public Material sand, rock, darkRock, concrete, steel, ivory, glass, rubber, copper, teal, cyan, blue, red, amber;
        private Transform buildRoot;
        private float motionTime;
        private float lastClick;
        private string lastId;
        private MaterialPropertyBlock propertyBlock;
        private Vector3[] outboundRoute, returnRoute;
        private Vector3[][] flowPaths;
        private Material[] flowMaterials;
        private float[] truckPhases;
        private bool[] hasTruckPhase;
        private string[] truckPoseStates;
        private bool poseWasLive;
        private float lastPoseHour;
        public Material[] strata;

        public void Build()
        {
            buildRoot = new GameObject("SITE · Актогай / Тыныс").transform;
            buildRoot.SetParent(transform, false);
            CreateMaterials();
            Terrain();
            Pit();
            Plant();
            Energy();
            Fleet();
            Connections();
            Labels();
            var labels = gameObject.GetComponent<MineSiteLabels>();
            if (labels == null) labels = gameObject.AddComponent<MineSiteLabels>();
            labels.world = this;
        }

        void CreateMaterials()
        {
            sand=Mat("01 · каменистая поверхность", "#697780", .08f);
            rock=Mat("02 · уступы", "#AC8060", .1f);
            darkRock=Mat("03 · нижние уступы", "#515965", .08f);
            strata=new[]{Mat("Пласт · песчаник","#BA9470",.08f),Mat("Пласт · охра","#996549",.09f),
                Mat("Пласт · известняк","#ACA795",.07f),Mat("Пласт · сланец","#596372",.12f),
                Mat("Пласт · медная руда","#9B6145",.12f),Mat("Пласт · порфир","#85786E",.09f),Mat("Пласт · основание","#465261",.1f)};
            concrete=Mat("04 · бетон", "#687B83", .12f);
            steel=Mat("05 · сталь", "#273D4B", .35f);
            ivory=Mat("06 · светлый металл", "#D6E3DD", .32f);
            glass=Mat("07 · стекло", "#77B6C4", .92f);
            glass.SetFloat("_Metallic",.12f);
            glass.color=new Color(.36f,.63f,.7f,.27f);
            glass.SetFloat("_Mode",3f);glass.SetInt("_SrcBlend",(int)BlendMode.One);glass.SetInt("_DstBlend",(int)BlendMode.OneMinusSrcAlpha);
            glass.SetInt("_ZWrite",0);glass.EnableKeyword("_ALPHAPREMULTIPLY_ON");glass.SetOverrideTag("RenderType","Transparent");glass.renderQueue=3000;
            rubber=Mat("08 · шины", "#18282D", .1f);
            copper=Mat("09 · медная руда", "#B66B43", .1f);
            teal=Mat("10 · энергия ВИЭ", "#52D6B5", .45f, true);
            cyan=Mat("11 · электроэнергия", "#66BBD7", .45f, true);
            blue=Mat("12 · фотоэлементы", "#245575", .55f);
            blue.SetFloat("_Glossiness",.91f);blue.SetFloat("_Metallic",.55f);
            red=Mat("13 · авария", "#EC765B", .35f, true);
            amber=Mat("14 · самосвалы", "#E7AC39", .28f);
            // One small shared texture adds mineral grain without extra draw calls or shader passes.
            var grain=new Texture2D(128,128,TextureFormat.RGB24,true){name="Минеральное зерно",wrapMode=TextureWrapMode.Repeat};
            for(int y=0;y<128;y++)for(int x=0;x<128;x++)
            {
                float fine=((x*73+y*151+x*y*19)%101)/100f;
                float value=.72f+.16f*Mathf.PerlinNoise(x*.12f,y*.12f)+.12f*fine;
                grain.SetPixel(x,y,new Color(value,value,value));
            }
            grain.Apply();
            foreach(var material in new[]{sand,rock,darkRock,concrete,copper})material.mainTexture=grain;
            foreach(var material in strata)material.mainTexture=grain;
        }

        Material Mat(string name,string hex,float smooth,bool emission=false)
        {
            ColorUtility.TryParseHtmlString(hex,out var col);
            var m=new Material(Shader.Find("Standard")) {name=name,color=col};
            m.SetFloat("_Glossiness",smooth);
            if(emission){m.EnableKeyword("_EMISSION");m.SetColor("_EmissionColor",col*.35f);}
            return m;
        }

        Transform Group(string name, Vector3 at, string id=null)
        {
            var t=new GameObject(name).transform;
            t.SetParent(buildRoot,false); t.localPosition=at;
            if(id!=null)t.gameObject.AddComponent<MineObject>().Id=id;
            return t;
        }

        GameObject Shape(PrimitiveType primitive,string name,Transform parent,Vector3 p,Vector3 s,Material material,Vector3 e=default)
        {
            var g=GameObject.CreatePrimitive(primitive);
            g.name=name;g.transform.SetParent(parent,false);
            g.transform.localPosition=p;g.transform.localScale=s;g.transform.localEulerAngles=e;
            g.GetComponent<Renderer>().sharedMaterial=material;
            return g;
        }
        GameObject Box(string n,Transform t,Vector3 p,Vector3 s,Material m,Vector3 e=default)
            =>Shape(PrimitiveType.Cube,n,t,p,s,m,e);
        GameObject Cyl(string n,Transform t,Vector3 p,Vector3 s,Material m,Vector3 e=default)
            =>Shape(PrimitiveType.Cylinder,n,t,p,s,m,e);

        void Beam(string n,Transform parent,Vector3 a,Vector3 b,float width,Material m)
        {
            var g=Box(n,parent,(a+b)*.5f,new Vector3(width,(b-a).magnitude,width),m);
            g.transform.localRotation=Quaternion.FromToRotation(Vector3.up,b-a);
        }
        GameObject MeshObject(string n,Transform t,List<Vector3> v,List<int> tri,Material m)
        {
            var mesh=new Mesh {name=n};
            mesh.SetVertices(v);mesh.SetTriangles(tri,0);
            var uv=new List<Vector2>(v.Count);
            foreach(var point in v)uv.Add(new Vector2(point.x*.24f,(point.z+point.y)*.24f));
            mesh.SetUVs(0,uv);mesh.RecalculateNormals();mesh.RecalculateBounds();
            var g=new GameObject(n,typeof(MeshFilter),typeof(MeshRenderer));
            g.transform.SetParent(t,false);
            g.GetComponent<MeshFilter>().sharedMesh=mesh;g.GetComponent<MeshRenderer>().sharedMaterial=m;
            g.AddComponent<MeshCollider>().sharedMesh=mesh;
            return g;
        }

        void Terrain()
        {
            var t=Group("00 · Ландшафт",Vector3.zero);
            var verts=new List<Vector3>();var tris=new List<int>();
            // Annulus connecting the pit rim to a rectangular island boundary.
            for(int i=0;i<=128;i++)
            {
                float a=i*Mathf.PI*2/128;float x=Mathf.Cos(a),z=Mathf.Sin(a);
                float tx=Mathf.Abs(x)<.00001f?float.PositiveInfinity:(x>0?128/x:-42/x);
                float tz=Mathf.Abs(z)<.00001f?float.PositiveInfinity:50/Mathf.Abs(z);
                float d=Mathf.Min(tx,tz);
                verts.Add(PitPoint(31,25,a,0)+new Vector3(-43,0,0));
                verts.Add(new Vector3(-43+d*x,0,d*z));
            }
            for(int i=0;i<128;i++){int j=i*2;tris.AddRange(new[]{j,j+2,j+1,j+1,j+2,j+3});}
            MeshObject("Степь · отверстие карьера",t,verts,tris,sand);
            // Side walls show this is a presentation model, not a geographic reconstruction.
            for(int layer=0;layer<7;layer++)
            {
                float depth=24f/7f,y=-(layer+.5f)*depth;
                var material=strata[layer];
                Box("Южный пласт "+layer,t,new Vector3(0,y,-50),new Vector3(170,depth,1),material);
                Box("Северный пласт "+layer,t,new Vector3(0,y,50),new Vector3(170,depth,1),material);
                Box("Западный пласт "+layer,t,new Vector3(-85,y,0),new Vector3(1,depth,100),material);
                Box("Восточный пласт "+layer,t,new Vector3(85,y,0),new Vector3(1,depth,100),material);
            }
            Box("Основание макета",t,new Vector3(0,-24.6f,0),new Vector3(172,1.5f,102),steel);
            foreach(float z in new[]{-51f,51f})
                Box("Контур основания",t,new Vector3(0,-24f,z),new Vector3(172,.12f,.12f),teal);
            foreach(float x in new[]{-86f,86f})
                Box("Контур основания",t,new Vector3(x,-24f,0),new Vector3(.12f,.12f,102),teal);
            // Sparse low polygon boulders use deterministic placement.
            for(int i=0;i<30;i++)
            {
                float x=-80+(i*31%160),z= i%2==0?46:-46;
                var b=Shape(PrimitiveType.Sphere,"Степной валун",t,new Vector3(x,.12f,z),new Vector3(1.2f+(i%3),.5f,1.1f),i%2==0?rock:darkRock);
                b.transform.localRotation=Quaternion.Euler(i*12,i*31,0);
            }
        }

        static Vector3 PitPoint(float radiusX,float radiusZ,float angle,float y)
        {
            float edge=.42f*Mathf.Sin(angle*7)+.18f*Mathf.Sin(angle*19);
            return new Vector3(Mathf.Cos(angle)*(radiusX+edge),y,Mathf.Sin(angle)*(radiusZ+edge));
        }

        void Ring(Transform t,string name,float outerX,float outerZ,float innerX,float innerZ,float y,float lowerY,Material m)
        {
            var v=new List<Vector3>();var tri=new List<int>();
            for(int i=0;i<=96;i++)
            {
                float a=i*Mathf.PI*2/96;
                v.Add(PitPoint(outerX,outerZ,a,y));
                v.Add(PitPoint(innerX,innerZ,a,y));
                v.Add(PitPoint(innerX,innerZ,a,lowerY));
            }
            for(int i=0;i<96;i++){int j=i*3;tri.AddRange(new[]{j,j+1,j+3,j+1,j+4,j+3,j+1,j+2,j+4,j+2,j+5,j+4});}
            MeshObject(name,t,v,tri,m);
        }
        void Pit()
        {
            var pit=Group("01 · Карьер",new Vector3(-43,0,0),"pit");
            for(int i=0;i<7;i++)
                Ring(pit,"Уступ "+(i+1),31-i*3.2f,25-i*2.5f,27.8f-i*3.2f,22.5f-i*2.5f,-i*2.3f,-(i+1)*2.3f,strata[i]);
            Cyl("Дно карьера",pit,new Vector3(0,-16.15f,0),new Vector3(18,.1f,15),darkRock);
            var road=new List<Vector3>();
            for(int i=0;i<=150;i++)
            {
                float f=i/150f,a=f*1.55f*Mathf.PI*2;
                road.Add(new Vector3(-43+Mathf.Cos(a)*(9+20*f),-15.8f+16*f,Mathf.Sin(a)*(7+16*f)));
            }
            // The fleet uses this same ramp geometry in Fleet().
            Excavator(pit,new Vector3(-3,-15.7f,2),15);
            Excavator(pit,new Vector3(12,-11.2f,0),-50);
            for(int i=0;i<9;i++)
                Shape(PrimitiveType.Sphere,"Руда в забое",pit,new Vector3(-3+i%4,-15.9f,6+i/4),new Vector3(1.2f,.8f,1),copper);
        }
        void Excavator(Transform parent,Vector3 p,float yaw)
        {
            var t=new GameObject("Экскаватор").transform;t.SetParent(parent,false);t.localPosition=p;t.localEulerAngles=new Vector3(0,yaw,0);
            Box("Гусеница L",t,new Vector3(-1,.45f,0),new Vector3(.8f,.9f,3.4f),rubber);
            Box("Гусеница R",t,new Vector3(1,.45f,0),new Vector3(.8f,.9f,3.4f),rubber);
            Box("Платформа",t,new Vector3(0,1.1f,0),new Vector3(2.9f,.8f,2.8f),amber);
            Box("Кабина",t,new Vector3(-.8f,2,0),new Vector3(1.2f,1.5f,1.5f),glass);
            Beam("Стрела",t,new Vector3(.5f,1.7f,0),new Vector3(.5f,5.7f,2),.5f,amber);
            Beam("Рукоять",t,new Vector3(.5f,5.7f,2),new Vector3(.5f,1.6f,5),.4f,amber);
            Box("Ковш",t,new Vector3(.5f,1,5),new Vector3(1.8f,1.3f,1.4f),steel,new Vector3(-25,0,0));
        }

        void Plant()
        {
            var piles=Group("02 · Раздельные склады",Vector3.zero);
            stockpiles=new Transform[2];
            for(int i=0;i<2;i++)
            {
                var t=Group(i==0?"Мягкая руда":"Твёрдая руда",new Vector3(-2,0,i==0?-11:11),i==0?"pile-soft":"pile-hard");
                t.SetParent(piles,true);
                Box("Подготовленная площадка",t,new Vector3(0,.12f,0),new Vector3(20,.24f,17),concrete);
                stockpiles[i]=new GameObject("Изменяемый запас руды").transform;stockpiles[i].SetParent(t,false);
                var v=new List<Vector3>();var tri=new List<int>();
                for(int j=0;j<32;j++)
                {
                    float a=j*Mathf.PI*2/32,b=(j+1)*Mathf.PI*2/32;int k=v.Count;
                    v.Add(new Vector3(0,7.5f,0));v.Add(new Vector3(8*Mathf.Cos(b),.3f,6*Mathf.Sin(b)));v.Add(new Vector3(8*Mathf.Cos(a),.3f,6*Mathf.Sin(a)));
                    tri.AddRange(new[]{k,k+1,k+2});
                }
                MeshObject("Рудный штабель",stockpiles[i],v,tri,i==0?rock:copper);
                Beam("Стрела стакера",t,new Vector3(-8,1,-5),new Vector3(0,9,0),.6f,ivory);
                Box("Привод стакера",t,new Vector3(-8,1,-5),new Vector3(2,2,2),steel);
            }
            mills=new Transform[2];lineStatus=new Renderer[2];steam=new ParticleSystem[2];
            for(int i=0;i<2;i++)
            {
                var t=Group("03 · Линия переработки "+(i+1),new Vector3(25,0,i==0?-13:10),"line-"+(i+1));
                Box("Фундамент",t,new Vector3(0,.25f,0),new Vector3(23,.5f,17),concrete);
                for(int x=-1;x<=1;x+=2) for(int z=-1;z<=1;z+=2)
                    Box("Колонна",t,new Vector3(x*9,4,z*6.5f),new Vector3(.65f,8,.65f),steel);
                Box("Стеклянная крыша",t,new Vector3(0,8.4f,1f),new Vector3(23,.16f,13.5f),glass);
                for(int rib=-2;rib<=2;rib++)Beam("Ребро крыши",t,new Vector3(rib*4.5f,8.55f,-5.7f),new Vector3(rib*4.5f,8.55f,7.7f),.17f,ivory);
                steam[i]=Steam(t,new Vector3(7,5,-3));
                Beam("Ферма крыши",t,new Vector3(-10,8.1f,-6),new Vector3(10,8.1f,-6),.35f,ivory);
                Box("Задняя стена",t,new Vector3(0,4.4f,7),new Vector3(21,8,.5f),steel);
                Box("Карниз",t,new Vector3(0,8.05f,-8.5f),new Vector3(23,.8f,.4f),teal);
                // Open southern wall exposes the processing equipment.
                var mill=Cyl("Мельница",t,new Vector3(0,3.8f,0),new Vector3(6,4,6),ivory,new Vector3(0,0,90));
                mills[i]=mill.transform;
                for(int band=-1;band<=1;band++)
                    Cyl("Бандаж",mill.transform,new Vector3(0,band*.6f,0),new Vector3(1.04f,.035f,1.04f),steel);
                Box("Опора мельницы",t,new Vector3(0,1.1f,0),new Vector3(10,1.6f,6),steel);
                Box("Двигатель",t,new Vector3(7,2,0),new Vector3(3,3,3),blue);
                lineStatus[i]=Box("Состояние линии",t,new Vector3(0,7.4f,-8.8f),new Vector3(17,.35f,.3f),teal).GetComponent<Renderer>();
                Conveyor(new Vector3(6,2,i==0?-11:11),new Vector3(16,4,i==0?-13:10));
            }
            var flot=Group("04 · Флотация",new Vector3(50,0,-5),"flotation");
            Box("Площадка флотации",flot,new Vector3(0,.18f,0),new Vector3(16,.36f,26),concrete);
            for(int i=0;i<6;i++)
            {
                float x=i%2*7-3.5f,z=i/2*7-7;
                Cyl("Флотокамера",flot,new Vector3(x,2,z),new Vector3(5.8f,2,5.8f),ivory);
                Cyl("Пульпа",flot,new Vector3(x,4.03f,z),new Vector3(5.35f,.05f,5.35f),blue);
                Beam("Мостик",flot,new Vector3(x-3,4.3f,z),new Vector3(x+3,4.3f,z),.3f,steel);
                Cyl("Привод мешалки",flot,new Vector3(x,4.8f,z),new Vector3(.8f,.5f,.8f),teal);
            }
            var concentrate=Group("05 · Сгуститель / концентрат",new Vector3(69,0,-10),"flotation");
            Cyl("Сгуститель",concentrate,new Vector3(0,1.7f,0),new Vector3(14,1.7f,14),ivory);
            Cyl("Вода",concentrate,new Vector3(0,3.45f,0),new Vector3(13,.05f,13),blue);
            Beam("Мост",concentrate,new Vector3(-7,3.8f,0),new Vector3(7,3.8f,0),.5f,steel);
            Box("Склад концентрата",concentrate,new Vector3(0,3,-17),new Vector3(13,6,9),steel);
            Box("Медный фасад",concentrate,new Vector3(0,3,-21.6f),new Vector3(11,4,.15f),copper);
            Conveyor(new Vector3(36,3,-13),new Vector3(45,3,-12));
            Conveyor(new Vector3(36,3,10),new Vector3(45,3,6));
        }
        void Conveyor(Vector3 a,Vector3 b)
        {
            var t=Group("Конвейер",Vector3.zero);
            Beam("Лента",t,a,b,1.2f,steel);
            Beam("Рудный поток",t,a+Vector3.up*.65f,b+Vector3.up*.65f,.45f,copper);
            for(int i=0;i<=3;i++)
            {
                var p=Vector3.Lerp(a,b,i/3f);
                Beam("Опора",t,new Vector3(p.x,0,p.z),p,.35f,ivory);
            }
        }

        ParticleSystem Steam(Transform parent,Vector3 position)
        {
            var g=new GameObject("Пар · иллюстративный эффект",typeof(ParticleSystem));
            g.transform.SetParent(parent,false);g.transform.localPosition=position;g.transform.localRotation=Quaternion.Euler(-90,0,0);
            var ps=g.GetComponent<ParticleSystem>();ps.Stop(true,ParticleSystemStopBehavior.StopEmittingAndClear);
            var main=ps.main;main.duration=6;main.loop=true;main.startLifetime=new ParticleSystem.MinMaxCurve(2.8f,4.5f);
            main.startSpeed=new ParticleSystem.MinMaxCurve(.7f,1.5f);main.startSize=new ParticleSystem.MinMaxCurve(1f,2.1f);
            main.startColor=new Color(.82f,.91f,.96f,.2f);main.maxParticles=50;main.simulationSpace=ParticleSystemSimulationSpace.World;
            main.playOnAwake=true;main.prewarm=true;
            var emission=ps.emission;emission.rateOverTime=5f;
            var shape=ps.shape;shape.shapeType=ParticleSystemShapeType.Cone;shape.angle=12;shape.radius=.6f;
            var velocity=ps.velocityOverLifetime;velocity.enabled=true;velocity.space=ParticleSystemSimulationSpace.World;
            velocity.x=.35f;velocity.y=1.1f;velocity.z=.1f;
            var size=ps.sizeOverLifetime;size.enabled=true;size.size=new ParticleSystem.MinMaxCurve(1,AnimationCurve.Linear(0,.35f,1,2f));
            var color=ps.colorOverLifetime;color.enabled=true;
            var gradient=new Gradient();gradient.SetKeys(new[]{new GradientColorKey(Color.white,0),new GradientColorKey(Color.white,1)},
                new[]{new GradientAlphaKey(0,0),new GradientAlphaKey(.65f,.2f),new GradientAlphaKey(0,1)});color.color=gradient;
            var tex=new Texture2D(32,32,TextureFormat.RGBA32,false){name="Мягкая частица пара",wrapMode=TextureWrapMode.Clamp};
            for(int x=0;x<32;x++)for(int y=0;y<32;y++)
            {
                float radius=new Vector2((x-15.5f)/15.5f,(y-15.5f)/15.5f).magnitude;
                tex.SetPixel(x,y,new Color(1,1,1,Mathf.Pow(Mathf.Clamp01(1-radius),2)));
            }
            tex.Apply();
            var material=new Material(Shader.Find("Particles/Standard Unlit")){name="Пар · полупрозрачный",mainTexture=tex};
            material.SetFloat("_Mode",2);material.SetInt("_SrcBlend",(int)BlendMode.SrcAlpha);material.SetInt("_DstBlend",(int)BlendMode.OneMinusSrcAlpha);
            material.SetInt("_ZWrite",0);material.EnableKeyword("_ALPHABLEND_ON");material.renderQueue=3000;
            var renderer=g.GetComponent<ParticleSystemRenderer>();renderer.sharedMaterial=material;renderer.renderMode=ParticleSystemRenderMode.Billboard;
            renderer.shadowCastingMode=ShadowCastingMode.Off;renderer.receiveShadows=false;
            return ps;
        }

        public static Vector3[] Spline(Vector3[] points,int subdivisions)
        {
            var samples=new List<Vector3>();
            for(int i=0;i<points.Length-1;i++)
            {
                Vector3 p0=points[Mathf.Max(0,i-1)],p1=points[i],p2=points[i+1],p3=points[Mathf.Min(points.Length-1,i+2)];
                for(int j=0;j<subdivisions;j++)
                {
                    float t=j/(float)subdivisions,t2=t*t,t3=t2*t;
                    samples.Add(.5f*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t2+(-p0+3*p1-3*p2+p3)*t3));
                }
            }
            samples.Add(points[points.Length-1]);return samples.ToArray();
        }

        void Energy()
        {
            var rot=new List<Transform>();
            for(int i=0;i<6;i++)
            {
                var p=new Vector3(-65+(i%3)*17,0,33+(i/3)*11);
                var t=Group("06 · Ветрогенератор "+(i+1),p,"wind");
                Cyl("Фундамент",t,new Vector3(0,.2f,0),new Vector3(4,.2f,4),concrete);
                Cyl("Башня",t,new Vector3(0,8,0),new Vector3(.7f,8,.7f),ivory);
                Box("Гондола",t,new Vector3(0,16,.7f),new Vector3(1.4f,1.4f,3),ivory);
                var r=new GameObject("Ротор").transform;r.SetParent(t,false);r.localPosition=new Vector3(0,16,-1);rot.Add(r);
                Shape(PrimitiveType.Sphere,"Втулка",r,Vector3.zero,Vector3.one*1.4f,ivory);
                for(int b=0;b<3;b++)
                {
                    var blade=new GameObject("Лопасть").transform;blade.SetParent(r,false);blade.localEulerAngles=new Vector3(0,0,b*120);
                    Box("Перо",blade,new Vector3(.3f,3.1f,0),new Vector3(.65f,5.7f,.19f),ivory,new Vector3(0,0,-4));
                    Box("Конец",blade,new Vector3(.65f,6.1f,0),new Vector3(.4f,1,.2f),teal);
                }
            }
            rotors=rot.ToArray();
            var solar=Group("07 · Солнечная станция",new Vector3(14,0,34),"pv");
            Box("Участок СЭС",solar,new Vector3(0,.12f,0),new Vector3(48,.24f,22),concrete);
            for(int i=0;i<48;i++)
            {
                float x=i%8*5.5f-19.25f,z=i/8*3.3f-8.25f;
                Box("Солнечная панель",solar,new Vector3(x,1.7f,z),new Vector3(4.8f,.2f,2.5f),blue,new Vector3(-22,0,0));
                Beam("Опора",solar,new Vector3(x,0,z),new Vector3(x,1.5f,z),.15f,steel);
                for(int j=-1;j<=1;j++)
                    Box("Разделитель ячеек",solar,new Vector3(x+j*1.2f,1.83f,z),new Vector3(.035f,.035f,2.4f),ivory,new Vector3(-22,0,0));
            }
            var bess=Group("08 · Накопитель энергии",new Vector3(28,0,-34),"bess");
            Box("Площадка АКБ",bess,new Vector3(0,.15f,0),new Vector3(25,.3f,12),concrete);
            batteryBars=new Renderer[6];
            for(int i=0;i<6;i++)
            {
                float x=i%3*7-7,z=i/3*5-2.5f;
                Box("Контейнер АКБ",bess,new Vector3(x,2,z),new Vector3(6,4,3.4f),ivory);
                for(int j=0;j<5;j++)Box("Ребро контейнера",bess,new Vector3(x-2+j,2,z-1.75f),new Vector3(.05f,3.5f,.08f),steel);
                batteryBars[i]=Box("Заряд АКБ",bess,new Vector3(x,4.1f,z),new Vector3(4.9f,.16f,2.5f),teal).GetComponent<Renderer>();
            }
            var grid=Group("09 · Подстанция",new Vector3(65,0,26),"substation");
            Box("Площадка подстанции",grid,new Vector3(0,.15f,0),new Vector3(25,.3f,26),concrete);
            for(int i=0;i<3;i++)
            {
                float x=-7+i*7;
                Box("Трансформатор",grid,new Vector3(x,2,0),new Vector3(4,4,5),steel);
                for(int j=0;j<4;j++)Box("Радиатор",grid,new Vector3(x-1.5f+j,2,-2.7f),new Vector3(.3f,3,.7f),ivory);
                for(int j=-1;j<=1;j++)Cyl("Изолятор",grid,new Vector3(x+j,4.8f,0),new Vector3(.35f,.8f,.35f),cyan);
            }
            for(int i=-1;i<=1;i+=2)
            {
                Beam("Портал",grid,new Vector3(i*9,0,8),new Vector3(i*9,10,8),.55f,steel);
                Beam("Траверса",grid,new Vector3(-10,10,8),new Vector3(10,10,8),.55f,steel);
            }
            var pylon=Group("10 · Ввод из сети",new Vector3(78,0,43),"substation");
            for(int i=-1;i<=1;i+=2)for(int j=-1;j<=1;j+=2)
                Beam("Стойка ЛЭП",pylon,new Vector3(i*2,0,j*2),new Vector3(i*.7f,16,j*.7f),.35f,steel);
            for(int y=4;y<=12;y+=4)
            {
                Beam("Раскос",pylon,new Vector3(-2,y-4,-2),new Vector3(2,y,-2),.15f,steel);
                Beam("Раскос",pylon,new Vector3(2,y-4,-2),new Vector3(-2,y,-2),.15f,steel);
            }
            for(int y=12;y<=16;y+=4)Beam("Траверса",pylon,new Vector3(-5,y,0),new Vector3(5,y,0),.4f,steel);
        }

        void Road(string name,Vector3[] points,float width,Material mat)
        {
            var g=new GameObject(name,typeof(LineRenderer));g.transform.SetParent(buildRoot,false);
            var lr=g.GetComponent<LineRenderer>();lr.sharedMaterial=mat;lr.positionCount=points.Length;lr.SetPositions(points);
            lr.startWidth=lr.endWidth=width;lr.alignment=LineAlignment.TransformZ;g.transform.rotation=Quaternion.Euler(90,0,0);
            lr.numCornerVertices=3;lr.shadowCastingMode=ShadowCastingMode.Off;lr.receiveShadows=true;
        }
        void Fleet()
        {
            var path=new List<Vector3>();
            for(int i=0;i<=150;i++)
            {
                float f=i/150f,a=f*1.55f*Mathf.PI*2;
                path.Add(new Vector3(-43+Mathf.Cos(a)*(9+20*f),-15.55f+16*f,Mathf.Sin(a)*(7+16*f)));
            }
            path.AddRange(new[]{new Vector3(-74,.4f,-17),new Vector3(-65,.4f,-29),
                new Vector3(-40,.4f,-28),new Vector3(-20,.4f,-24),new Vector3(-12,.4f,-16)});
            // Sample Catmull-Rom curves once; both road and trucks share the smooth path.
            path = new List<Vector3>(Spline(path.ToArray(),5));
            outboundCount=path.Count;
            Road("Дорога самосвалов",path.ToArray(),3.2f,rock);
            for(int i=outboundCount-2;i>=0;i--)path.Add(path[i]);
            route=path.ToArray();
            Road("Дорога к зарядке",new[]{new Vector3(-40,.3f,-28),new Vector3(-25,.3f,-37),new Vector3(6,.3f,-37)},3,rock);
            var charging=Group("11 · Зарядка флота",new Vector3(-12,0,-35),"pit");
            Box("Зарядная площадка",charging,new Vector3(0,.1f,0),new Vector3(29,.2f,13),concrete);
            for(int i=0;i<4;i++)
            {
                float x=i*6.5f-10;
                Box("Зарядная станция",charging,new Vector3(x,2,2),new Vector3(2.4f,4,1.5f),steel);
                Box("Индикатор",charging,new Vector3(x,2.6f,1.2f),new Vector3(1.6f,1.6f,.16f),teal);
                Beam("Кабель",charging,new Vector3(x,2.6f,1),new Vector3(x+1.5f,.3f,-1),.14f,rubber);
                Box("Разметка",charging,new Vector3(x,.25f,-3),new Vector3(4,.05f,4),ivory);
            }
            trucks=new Transform[14];truckLoads=new Transform[14];truckHeadlights=new Light[28];
            var lamp=Mat("Фары · тёплый свет","#FFF3C2",.75f,true);
            lamp.SetColor("_EmissionColor",new Color(2.2f,1.9f,1.3f));
            for(int i=0;i<14;i++)
            {
                var t=Group("Самосвал · звено "+(i+1),route[i%route.Length],"truck-"+(i+1).ToString("00"));
                trucks[i]=t;
                Box("Шасси",t,new Vector3(0,.9f,0),new Vector3(2.4f,.7f,4.2f),steel);
                Box("Кабина",t,new Vector3(0,1.8f,1.25f),new Vector3(2.6f,1.5f,1.6f),amber);
                Box("Стекло",t,new Vector3(0,2.1f,2.07f),new Vector3(2.1f,.7f,.1f),glass);
                for(int side=0;side<2;side++)
                {
                    float lampX=side==0?-.86f:.86f;
                    Box("Фара",t,new Vector3(lampX,1.35f,2.1f),new Vector3(.5f,.32f,.15f),lamp);
                    var head=new GameObject("Луч фары",typeof(Light));head.transform.SetParent(t,false);
                    head.transform.localPosition=new Vector3(lampX,1.4f,2.2f);head.transform.localEulerAngles=new Vector3(12,0,0);
                    var source=head.GetComponent<Light>();source.type=LightType.Spot;source.spotAngle=52;source.innerSpotAngle=30;
                    source.color=new Color(1,.91f,.68f);source.intensity=2.2f;source.range=15;source.shadows=LightShadows.None;
                    truckHeadlights[i*2+side]=source;
                }
                Box("Кузов",t,new Vector3(0,1.8f,-.9f),new Vector3(3,1.1f,2.8f),amber);
                Box("Борт L",t,new Vector3(-1.45f,2.55f,-.9f),new Vector3(.17f,.7f,2.9f),amber);
                Box("Борт R",t,new Vector3(1.45f,2.55f,-.9f),new Vector3(.17f,.7f,2.9f),amber);
                truckLoads[i]=Shape(PrimitiveType.Sphere,"Груз",t,new Vector3(0,2.4f,-.9f),new Vector3(2.6f,.9f,2.4f),copper).transform;
                for(int x=-1;x<=1;x+=2)for(int z=-1;z<=1;z+=2)
                    Cyl("Колесо",t,new Vector3(x*1.45f,.8f,z*1.25f),new Vector3(1.5f,.35f,1.5f),rubber,new Vector3(0,0,90));
            }
        }

        LineRenderer Flow(string name,Vector3[] points,Material mat,float width)
        {
            var g=new GameObject(name,typeof(LineRenderer));g.transform.SetParent(buildRoot,false);
            var l=g.GetComponent<LineRenderer>();l.sharedMaterial=mat;l.positionCount=points.Length;l.SetPositions(points);
            l.startWidth=l.endWidth=width;l.numCornerVertices=4;l.numCapVertices=4;l.shadowCastingMode=ShadowCastingMode.Off;
            return l;
        }
        void Connections()
        {
            energyFlows=new[]{
                Flow("Энергия · ВЭС",new[]{new Vector3(-26,1,36),new Vector3(-17,1,24),new Vector3(62,1,24)},teal,.35f),
                Flow("Энергия · СЭС",new[]{new Vector3(36,1,34),new Vector3(62,1,34),new Vector3(62,1,24)},teal,.35f),
                Flow("Энергия · сеть",new[]{new Vector3(78,13,43),new Vector3(65,10,34),new Vector3(62,1,24)},cyan,.35f),
                Flow("Энергия · фабрика",new[]{new Vector3(62,1,24),new Vector3(41,1,24),new Vector3(41,1,-24),new Vector3(25,1,-24)},cyan,.35f),
                Flow("Энергия · АКБ",new[]{new Vector3(62,1,24),new Vector3(61,1,-34),new Vector3(38,1,-34)},teal,.35f),
                Flow("Энергия · флот",new[]{new Vector3(38,1,-34),new Vector3(10,1,-25),new Vector3(-12,1,-25),new Vector3(-12,1,-32)},cyan,.35f)};
            oreFlows=new[]{
                Flow("Руда · мягкая",new[]{new Vector3(0,1,-11),new Vector3(10,1,-11),new Vector3(25,1,-13)},copper,.8f),
                Flow("Руда · твёрдая",new[]{new Vector3(0,1,11),new Vector3(10,1,11),new Vector3(25,1,10)},copper,.8f)};
            var pulse=new Texture2D(64,8,TextureFormat.RGBA32,false){name="Энергия · бегущий импульс",wrapMode=TextureWrapMode.Repeat,filterMode=FilterMode.Bilinear};
            for(int x=0;x<64;x++)for(int y=0;y<8;y++)
            {
                float peak=Mathf.Pow(Mathf.Clamp01(1-Mathf.Abs(x-40)/18f),2);
                pulse.SetPixel(x,y,new Color(.25f+peak*1.75f,.25f+peak*1.75f,.25f+peak*1.75f,.45f+peak*.55f));
            }
            pulse.Apply();
            for(int i=0;i<energyFlows.Length;i++)
            {
                var flowMaterial=new Material(Shader.Find("Tynys/EnergyFlow")){name="Энергия · материал "+i,mainTexture=pulse};
                flowMaterial.SetColor("_Color",i==0||i==1||i==4?new Color(.22f,1.6f,1.2f):new Color(.3f,1.1f,1.8f));
                energyFlows[i].sharedMaterial=flowMaterial;energyFlows[i].textureMode=LineTextureMode.Tile;
            }
            flowDots=new Transform[energyFlows.Length*3];
            for(int i=0;i<flowDots.Length;i++)
                flowDots[i]=Shape(PrimitiveType.Sphere,"Поток энергии",buildRoot,Vector3.zero,Vector3.one*.65f,i/3==2?cyan:teal).transform;
        }

        void Labels()
        {
            // Physical site labels are Latin to remain portable with Unity's built-in 3D font.
            // Full Russian labels and values are in the HUD and selection panel.
            Label("AKTOGAY  /  TYNYS",new Vector3(-57,1,-39),2.0f,ivory);
            Label("WIND",new Vector3(-31,1,26),1.1f,ivory);
            Label("SOLAR",new Vector3(12,1,22),1.1f,ivory);
            Label("SOFT",new Vector3(-5,1,-21),1.05f,ivory);
            Label("HARD",new Vector3(-5,1,20),1.05f,ivory);
            Label("01",new Vector3(24,9,-13),2.2f,steel);
            Label("02",new Vector3(24,9,10),2.2f,steel);
            Label("BESS",new Vector3(25,1,-42),1.1f,ivory);
            Label("GRID",new Vector3(64,1,11),1.1f,ivory);
        }
        void Label(string label,Vector3 p,float size,Material mat)
        {
            var g=new GameObject(label,typeof(TextMesh));g.transform.SetParent(buildRoot,false);g.transform.localPosition=p;
            g.transform.localEulerAngles=new Vector3(70,0,0);
            var text=g.GetComponent<TextMesh>();text.text=label;text.characterSize=size*.1f;text.fontSize=80;text.anchor=TextAnchor.MiddleCenter;
            text.color=mat.color;
        }

        void Start()
        {
            propertyBlock=new MaterialPropertyBlock();
            if(trucks==null || trucks.Length==0)Build();
            outboundRoute=new Vector3[outboundCount];
            System.Array.Copy(route,0,outboundRoute,0,outboundCount);
            returnRoute=new Vector3[route.Length-outboundCount+1];
            System.Array.Copy(route,outboundCount-1,returnRoute,0,returnRoute.Length);
            ResetTruckPoses();
            flowPaths=new Vector3[energyFlows.Length][];flowMaterials=new Material[energyFlows.Length];
            for(int i=0;i<energyFlows.Length;i++)
            {
                flowPaths[i]=new Vector3[energyFlows[i].positionCount];energyFlows[i].GetPositions(flowPaths[i]);
                flowMaterials[i]=energyFlows[i].material;
            }
        }
        void Update()
        {
            if(data==null || data.State==null)return;
            var s=data.State;
            bool animate=!data.Paused&&(!data.LiveMode||(data.IsConnected&&!data.IsStale));
            if(!data.HasSnapshot)
            {
                foreach(var ps in steam)if(ps!=null)ps.Pause();
                foreach(var dot in flowDots)dot.gameObject.SetActive(false);
                return;
            }
            if(poseWasLive!=data.LiveMode||(!data.LiveMode&&s.hour<lastPoseHour-.001f))ResetTruckPoses();
            poseWasLive=data.LiveMode;lastPoseHour=s.hour;
            if(animate)motionTime+=Time.deltaTime;
            for(int i=0;i<rotors.Length;i++)
                if(animate)rotors[i].Rotate(0,0,Time.deltaTime*Mathf.Clamp(s.windMW/300f,0,1)*120);
            for(int i=0;i<stockpiles.Length;i++)
                stockpiles[i].localScale=new Vector3(1,Mathf.Lerp(.12f,1,Mathf.Clamp01((i==0?s.pileSoftPct:s.pileHardPct)/100)),1);
            for(int i=0;i<2;i++)
            {
                bool running=(i==0?s.line1Available:s.line2Available)&&(i==0?s.line1Feed:s.line2Feed)>1;
                if(running&&animate)mills[i].Rotate(0,Time.deltaTime*25,0,Space.Self);
                SetColor(lineStatus[i],running?teal.color:red.color);
                if(steam!=null&&i<steam.Length&&steam[i]!=null)
                {
                    var emission=steam[i].emission;emission.enabled=running;
                    if(animate) { if(!steam[i].isPlaying)steam[i].Play(); }
                    else steam[i].Pause();
                }
            }
            foreach(var bar in batteryBars)
            {
                bar.transform.localScale=new Vector3(4.9f*Mathf.Max(.03f,s.bessSoc/100),.16f,2.5f);
                SetColor(bar,s.bessAvailable?teal.color:red.color);
            }
            for(int i=0;i<trucks.Length;i++)
            {
                var tr=s.trucks!=null&&i<s.trucks.Length?s.trucks[i]:null;
                UpdateTruckPose(i,tr??new TruckState{state="empty",routePos=(motionTime*.014f+i/14f)%1},animate,Time.deltaTime);
                truckLoads[i].gameObject.SetActive(tr!=null&&tr.state=="loaded");
                if(truckHeadlights!=null&&truckHeadlights.Length>i*2+1)
                    for(int side=0;side<2;side++)truckHeadlights[i*2+side].enabled=MinePlatform.AllowTruckLights&&tr!=null&&(tr.state=="loaded"||tr.state=="empty");
            }
            float[] amounts={s.windMW,s.pvMW,s.gridMW,s.loadMW,s.bessAvailable?Mathf.Abs(s.bessMW):0,s.chargeMW};
            for(int i=0;i<energyFlows.Length;i++)
            {
                var flow=energyFlows[i];float val=Mathf.Max(0,amounts[i]);
                flow.startWidth=flow.endWidth=.09f+Mathf.Clamp01(val/250)*.65f;
                flowMaterials[i].SetFloat("_FlowOffset",motionTime*(i==4&&s.bessMW>0?1:-1)*.65f);
                flowMaterials[i].SetFloat("_Strength",val>1?1:.12f);
                for(int j=0;j<3;j++)
                {
                    var dot=flowDots[i*3+j];dot.gameObject.SetActive(val>1);
                    var pts=flowPaths[i];
                    float phase=(motionTime*.12f+j/3f)%1;
                    if(i==4&&s.bessMW>0)phase=1-phase;
                    dot.position=Along(pts,phase,out _);
                }
            }
            oreFlows[0].startWidth=oreFlows[0].endWidth=.18f+Mathf.Clamp01(s.line1Feed/4000)*1.0f;
            oreFlows[1].startWidth=oreFlows[1].endWidth=.18f+Mathf.Clamp01(s.line2Feed/4000)*1.0f;
            if(Input.GetMouseButtonDown(0)&&cameraRig!=null&&!cameraRig.IsPointerOverUI())
            {
                var ray=viewCamera.ScreenPointToRay(Input.mousePosition);
                if(Physics.Raycast(ray,out var hit,500))
                {
                    var obj=hit.collider.GetComponentInParent<MineObject>();
                    if(obj!=null)
                    {
                        hud.Select(obj.Id);
                        if(lastId==obj.Id&&Time.unscaledTime-lastClick<.3f)cameraRig.Focus(obj.transform.position);
                        lastId=obj.Id;lastClick=Time.unscaledTime;
                    }
                }
            }
        }
        public void ResetTruckPoses()
        {
            truckPhases=new float[trucks.Length];hasTruckPhase=new bool[trucks.Length];truckPoseStates=new string[trucks.Length];
        }

        internal float TruckVisualPhase(int index) => truckPhases==null?0:truckPhases[index];

        /// <summary>LIVE uses a local illustrative 90-second lap; DEMO follows its continuous phase.</summary>
        public void UpdateTruckPose(int index,TruckState telemetry,bool animate,float deltaTime)
        {
            bool travel=telemetry.state=="loaded"||telemetry.state=="empty";
            if(!travel)
            {
                // Telemetry has no route from the haul road into a bay. Show a discrete
                // schematic state change instead of inventing a straight-line GPS trip.
                if(truckPoseStates[index]!=telemetry.state)
                {
                    bool charging=telemetry.state=="charging";
                    trucks[index].position=charging?new Vector3(-22+(index%4)*6.5f,.3f,-38+(index/4)*2.5f):
                        new Vector3(-24+(index%5)*5.5f,.3f,-29+(index/5)*2.5f);
                    trucks[index].rotation=Quaternion.identity;
                }
                hasTruckPhase[index]=false;truckPoseStates[index]=telemetry.state;
                return;
            }
            float targetPhase=Mathf.Repeat(telemetry.routePos,1);
            bool initialize=!hasTruckPhase[index];
            if(initialize)truckPhases[index]=targetPhase;
            else if(animate)
            {
                if(data!=null&&data.LiveMode)
                {
                    // Backend route_pos is an illustrative seed, now published once/model hour.
                    // Chasing its +0.7 hourly alias would move backwards and stop between polls.
                    // State/payload remain authoritative; geometry advances locally, never GPS.
                    truckPhases[index]=Mathf.Repeat(truckPhases[index]+Mathf.Max(0,deltaTime)/90f,1);
                }
                else
                {
                    float delta=Mathf.Repeat(targetPhase-truckPhases[index]+.5f,1)-.5f;
                    truckPhases[index]=Mathf.Repeat(truckPhases[index]+delta*(1-Mathf.Exp(-deltaTime*8)),1);
                }
            }
            float phase=truckPhases[index];
            var points=phase<.5f?outboundRoute:returnRoute;
            var point=Along(points,phase<.5f?phase*2:(phase-.5f)*2,out var tangent);
            trucks[index].position=point+Vector3.Cross(Vector3.up,tangent.normalized)*.7f;
            if(tangent.sqrMagnitude>.001f)
            {
                var rotation=Quaternion.LookRotation(tangent.normalized,Vector3.up);
                if(initialize)trucks[index].rotation=rotation;
                else if(animate)trucks[index].rotation=Quaternion.Slerp(trucks[index].rotation,rotation,1-Mathf.Exp(-deltaTime*6));
            }
            hasTruckPhase[index]=true;truckPoseStates[index]=telemetry.state;
        }

        void SetColor(Renderer r,Color c)
        {
            r.GetPropertyBlock(propertyBlock);propertyBlock.SetColor("_Color",c);propertyBlock.SetColor("_EmissionColor",c*.35f);r.SetPropertyBlock(propertyBlock);
        }
        public static Vector3 Along(Vector3[] points,float phase,out Vector3 tangent)
        {
            float total=0;for(int i=1;i<points.Length;i++)total+=Vector3.Distance(points[i-1],points[i]);
            float d=Mathf.Repeat(phase,1)*total;
            for(int i=1;i<points.Length;i++)
            {
                float len=Vector3.Distance(points[i-1],points[i]);
                if(d<=len){tangent=points[i]-points[i-1];return Vector3.Lerp(points[i-1],points[i],len>0?d/len:0);}
                d-=len;
            }
            tangent=Vector3.forward;return points[0];
        }
    }
}
