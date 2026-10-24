using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Tynys
{
    /// <summary>Screen-facing labels anchored to the editable 3D site. Values share HUD provenance.</summary>
    public sealed class MineSiteLabels : MonoBehaviour
    {
        public MineWorld world;
        static readonly List<Rect> hitRects=new List<Rect>();
        readonly string[] ids={"wind","pv","substation","line-1","line-2","bess"};
        readonly string[] titles={"ВЭС","СЭС","СЕТЬ","ЛИНИЯ 1","ЛИНИЯ 2","BESS"};
        readonly Vector3[] anchors={new Vector3(-50,6,27),new Vector3(14,4,35),new Vector3(65,11,26),
            new Vector3(25,11,-13),new Vector3(25,11,10),new Vector3(28,6,-34)};
        GUIStyle style;
        public static bool PointerOverLabel(Vector3 point)
        {
            var p=new Vector2(point.x,Screen.height-point.y);
            foreach(var rect in hitRects)if(rect.Contains(p))return true;
            return false;
        }
        void OnGUI()
        {
            hitRects.Clear();
            if(world==null||world.data==null||world.hud==null||!world.hud.Visible||world.viewCamera==null)return;
            if(world.hud.command!=null&&!world.hud.command.SiteView)return;
            if(style==null)
            {
                var font=MinePlatform.UiFont;
                style=new GUIStyle(GUI.skin.label){font=font,fontSize=13,alignment=TextAnchor.MiddleCenter,fontStyle=FontStyle.Bold,richText=false,wordWrap=false};
                style.normal.textColor=new Color(.9f,.98f,.97f);
            }
            float scale=Mathf.Min(Screen.width/1600f,Screen.height/900f);
            var s=world.data.State;bool valid=world.data.HasSnapshot&&s!=null;
            GUI.depth=1;
            style.fontSize=Mathf.RoundToInt(13*scale);
            for(int i=0;i<anchors.Length;i++)
            {
                var screen=world.viewCamera.WorldToScreenPoint(anchors[i]);
                if(screen.z<0)continue;
                float y=Screen.height-screen.y;
                var rect=new Rect(screen.x-66*scale,y-17*scale,132*scale,34*scale);
                if(rect.x<300*scale||rect.xMax>Screen.width-350*scale||rect.y<156*scale||rect.yMax>Screen.height-205*scale)continue;
                bool collision=false;foreach(var previous in hitRects)if(previous.Overlaps(rect)){collision=true;break;}
                if(collision)continue;
                string value="—";
                if(valid)
                {
                    float amount=i==0?s.windMW:i==1?s.pvMW:i==2?s.gridMW:i==3?s.line1Feed:i==4?s.line2Feed:s.bessSoc;
                    value=amount.ToString(i==3||i==4?"0":"0.0",CultureInfo.InvariantCulture)+(i==3||i==4?" т/ч":i==5?"% SoC":" МВт");
                }
                var color=GUI.color;
                GUI.color=MinePlatform.GuiColor(new Color(.025f,.055f,.075f,.95f));GUI.DrawTexture(rect,Texture2D.whiteTexture);
                GUI.color=MinePlatform.GuiColor(new Color(.4f,.87f,.8f,.75f));
                GUI.DrawTexture(new Rect(rect.x,rect.y,2*scale,rect.height),Texture2D.whiteTexture);
                GUI.color=color;
                string suffix=valid&&world.data.LiveMode&&world.data.IsStale?" · архив":"";
                GUI.Label(rect,titles[i]+suffix+"\n"+value,style);
                hitRects.Add(rect);
                if(Event.current.type==EventType.MouseDown&&Event.current.button==0&&rect.Contains(Event.current.mousePosition))
                { world.hud.Select(ids[i]);Event.current.Use(); }
            }
            GUI.depth=0;
        }
        void OnDisable(){hitRects.Clear();}
    }
}
