using System.Globalization;
using System.Collections.Generic;
using UnityEngine;

namespace Tynys
{
    /// <summary>Russian runtime UI. All demo values are explicitly illustrative.</summary>
    public sealed class MineHUD : MonoBehaviour
    {
        public MineData data;
        public MineCamera cameraRig;
        public MineCommandView command;
        public string SelectedId = "pit";
        public bool Visible = true;
        public static bool IsTyping { get; private set; }

        private readonly Color background = Hex(0x0B141D);
        private readonly Color surface = Hex(0x11232D);
        private readonly Color raised = Hex(0x1B3440);
        private readonly Color teal = Hex(0x66DFCB);
        private readonly Color sand = Hex(0xE7C595);
        private readonly Color ink = Hex(0xEDF4F3);
        private readonly Color muted = Hex(0x9DB4BA);
        private readonly Color orange = Hex(0xF3A67A);
        private GUIStyle panel, small, body, title, number, eyebrow, button, field, badge;
        private Texture2D rounded;
        private Font font;
        private string endpoint = "";
        private bool endpointInitialized;
        private bool fast;
        private bool initialized;
        private float uiWidth, uiHeight;
        private readonly List<float> powerHistory=new List<float>();
        private readonly List<Rect> truckLabelRects=new List<Rect>();
        private Texture2D gaugeRing,batteryGauge,gridGauge;
        private int lastBattery=-1,lastGrid=-1;
        private float nextSample;
        private bool historyLive;
        private bool HasSnapshot
        {
            get
            {
                return data != null && data.State != null && data.HasSnapshot;
            }
        }
        private readonly string[] objectIds = {
            "pit", "pile-soft", "pile-hard", "line-1", "line-2", "wind", "pv", "bess", "substation"
        };
        private readonly string[] objectNames = {
            "Карьер", "Мягкая руда", "Твёрдая руда", "Линия 1", "Линия 2", "ВЭС", "СЭС", "BESS", "Подстанция"
        };
        private readonly string[] eventNames = {
            "1  БАЗОВЫЙ", "2  ШТИЛЬ", "3  СТОП ЛИНИИ", "4  ЛИМИТ СЕТИ",
            "5  ТВЁРДАЯ РУДА", "6  ПЛАН +", "7  СБОЙ BESS"
        };
        private readonly DemoScenario[] events = {
            DemoScenario.Normal, DemoScenario.Lull, DemoScenario.LineTrip,
            DemoScenario.Kegoc, DemoScenario.HardOre, DemoScenario.PlanUp, DemoScenario.BessFault
        };

        private void Awake()
        {
            if (cameraRig == null) cameraRig = FindFirstObjectByType<MineCamera>();
            if (data == null) data = FindFirstObjectByType<MineData>();
            if (cameraRig != null) cameraRig.hud = this;
        }

        private void Update()
        {
            if (IsTyping) return;
            if (Input.GetKeyDown(KeyCode.H)) Visible = !Visible;
            if (data == null) return;
            if(historyLive!=data.LiveMode){historyLive=data.LiveMode;powerHistory.Clear();}
            if(HasSnapshot&&!data.IsStale&&Time.realtimeSinceStartup>=nextSample)
            {
                nextSample=Time.realtimeSinceStartup+1;
                powerHistory.Add(data.State.loadMW);if(powerHistory.Count>18)powerHistory.RemoveAt(0);
            }
            if (!data.LiveMode)
            {
                if (Input.GetKeyDown(KeyCode.Space)) data.Paused = !data.Paused;
                for (int i = 0; i < events.Length; i++)
                {
                    if (Input.GetKeyDown((KeyCode)((int)KeyCode.Alpha1 + i)))
                        data.SetScenario(events[i]);
                }
            }
        }

        public void Select(string id)
        {
            if (string.IsNullOrEmpty(id)) return;
            SelectedId = id;
            if (cameraRig == null) return;
            if(command!=null)
            {
                if(id=="pit"){command.ShowSite(false);return;}
                if(!command.SiteView&&id.StartsWith("truck-")&&int.TryParse(id.Substring(6),out int index)&&index>=1&&index<=command.trucks.Length)
                {cameraRig.Focus(command.trucks[index-1].position);return;}
                command.ShowSite(true);
            }
            var objects = FindObjectsByType<MineObject>(FindObjectsSortMode.None);
            Vector3 center = Vector3.zero;
            int count = 0;
            foreach (var obj in objects)
                if (obj.Id == id) { center += obj.transform.position; count++; }
            if (count > 0) cameraRig.Focus(center / count);
        }

        public bool ContainsScreenPoint(Vector3 point)
        {
            float scale = Mathf.Min(Screen.width / 1600f, Screen.height / 900f);
            float w = Screen.width / scale, h = Screen.height / scale;
            Vector2 p = new Vector2(point.x / scale, (Screen.height - point.y) / scale);
            foreach(var rect in truckLabelRects)if(rect.Contains(p))return true;
            return MineSiteLabels.PointerOverLabel(point) || p.y <= 154f || p.y >= h - 224f || p.x >= w - 344f || p.x<=290;
        }

        private void SetupStyles()
        {
            if (initialized) return;
            initialized = true;
            font = MinePlatform.UiFont;
            rounded = new Texture2D(24, 24, TextureFormat.RGBA32, false);
            rounded.name = "Tynys UI corners";
            rounded.hideFlags = HideFlags.HideAndDontSave;
            rounded.filterMode = FilterMode.Bilinear;
            for (int y = 0; y < 24; y++)
                for (int x = 0; x < 24; x++)
                {
                    float dx = Mathf.Max(1.5f - x, x - 21.5f, 0f);
                    float dy = Mathf.Max(1.5f - y, y - 21.5f, 0f);
                    float a = Mathf.Clamp01(2f - Mathf.Sqrt(dx * dx + dy * dy));
                    rounded.SetPixel(x, y, new Color(1f, 1f, 1f, a));
                }
            rounded.Apply();
            panel = new GUIStyle { border = new RectOffset(2, 2, 2, 2) };
            panel.normal.background = rounded;
            small = TextStyle(13, muted);
            body = TextStyle(16, ink);
            title = TextStyle(29, ink, FontStyle.Bold);
            number = TextStyle(27, ink, FontStyle.Bold);
            eyebrow = TextStyle(11, muted, FontStyle.Bold);
            button = TextStyle(12, ink, FontStyle.Bold);
            button.alignment = TextAnchor.MiddleCenter;
            button.normal.background = rounded;
            button.hover.background = rounded;
            button.active.background = rounded;
            button.border = new RectOffset(2, 2, 2, 2);
            button.padding = new RectOffset(6, 6, 2, 2);
            field = TextStyle(12, ink);
            field.normal.background = rounded;
            field.focused.background = rounded;
            field.border = new RectOffset(2, 2, 2, 2);
            field.padding = new RectOffset(9, 9, 6, 4);
            field.clipping = TextClipping.Clip;
            badge = TextStyle(11, teal, FontStyle.Bold);
            badge.alignment = TextAnchor.MiddleCenter;
        }

        private GUIStyle TextStyle(int size, Color color, FontStyle weight = FontStyle.Normal)
        {
            var style = new GUIStyle(GUI.skin.label)
            {
                font = font, fontSize = size, fontStyle = weight,
                wordWrap = false, padding = new RectOffset(0, 0, 0, 0),
                margin = new RectOffset(0, 0, 0, 0), richText = false
            };
            style.normal.textColor = color;
            style.hover.textColor = color;
            style.active.textColor = color;
            style.focused.textColor = color;
            return style;
        }

        private void OnGUI()
        {
            SetupStyles();
            if (!Visible)
            {
                GUI.Label(new Rect(16f, 14f, 320f, 22f), "H — показать панель • Home — общий вид", small);
                IsTyping = false;
                return;
            }
            float scale = Mathf.Min(Screen.width / 1600f, Screen.height / 900f);
            uiWidth = Screen.width / scale;
            uiHeight = Screen.height / scale;
            Matrix4x4 oldMatrix = GUI.matrix;
            Color oldColor = GUI.color;
            GUI.matrix = Matrix4x4.TRS(Vector3.zero, Quaternion.identity, Vector3.one * scale);
            GUI.color = Color.white;

            if (data == null)
            {
                Box(new Rect(20, 20, 620, 90), background);
                Label(40, 38, 560, 24, "ТЫНЫС / подготовка цифрового двойника", body);
                GUI.matrix = oldMatrix;
                GUI.color = oldColor;
                return;
            }
            if (!endpointInitialized)
            {
                endpoint = data.Endpoint ?? "";
                endpointInitialized = true;
            }
            DrawHeader();
            DrawTelemetry();
            DrawSceneTools();
            DrawTruckLabels(scale);
            DrawInspector();
            DrawScenarios();
            IsTyping = GUI.GetNameOfFocusedControl() == "tynys-endpoint";
            GUI.matrix = oldMatrix;
            GUI.color = oldColor;
        }

        private void DrawHeader()
        {
            var s = data.State;
            bool hasSnapshot = HasSnapshot;
            Box(new Rect(16, 16, uiWidth - 32, 80), background);
            Label(36, 24, 225, 37, "ТЫНЫС", title);
            Label(38, 65, 440, 16, "АКТОГАЙ  /  ЭНЕРГИЯ · РУДА · МЕДЬ", eyebrow);
            bool live = data.LiveMode;
            bool healthy = live && data.IsConnected && !data.IsStale;
            Color stateColor = healthy ? teal : live ? orange : sand;
            Chip(new Rect(208, 33, 96, 25), live ? "LIVE" : "ДЕМО", stateColor);
            Label(320, 29, 200, 21, hasSnapshot ? s.simTime ?? "—" : "—", body);
            Label(320, 57, 200, 18, live ? (!hasSnapshot ? "ожидание данных" :
                data.IsStale ? "данные устарели" : "телеметрия OpenEgiz") : "учебная симуляция", small);

            float kpiX = 532f, gap = 12f;
            float width = (uiWidth - kpiX - 36f - 2f * gap) / 3f;
            Kpi(new Rect(kpiX, 24, width, 64), "НАГРУЗКА", hasSnapshot ? F(s.loadMW) + " МВт" : "—",
                hasSnapshot ? "сеть " + F(s.gridMW) + " / " + F(s.gridCapMW) + " МВт" : "нет снимка", sand);
            Kpi(new Rect(kpiX + width + gap, 24, width, 64), "ДОЛЯ ВИЭ", hasSnapshot ? Percent(s.renewShare) : "—",
                hasSnapshot ? "ветер " + F(s.windMW) + " · солнце " + F(s.pvMW) + " МВт" : "нет снимка", teal);
            Kpi(new Rect(kpiX + (width + gap) * 2f, 24, width, 64), "ВЫХОД МЕДИ", hasSnapshot ? F(s.cuTPH) + " т/ч" : "—",
                hasSnapshot ? "подача " + F(s.feedTPH, "0") + " т/ч" : "нет снимка", sand);
        }

        private void Kpi(Rect r, string caption, string value, string note, Color accent)
        {
            Box(r, surface);
            Fill(new Rect(r.x + 12, r.y + 12, 3, 40), accent);
            Label(r.x + 26, r.y + 8, r.width - 34, 15, caption, eyebrow);
            Label(r.x + 26, r.y + 27, r.width - 34, 34, value, number);
            // Place the operational detail to the right when room permits.
            float noteWidth = Mathf.Max(110f, r.width - 202f);
            Label(r.xMax - noteWidth - 12, r.y + 11, noteWidth, 40, note, small, true, TextAnchor.MiddleRight);
        }

        private void DrawSceneTools()
        {
            float centerWidth=uiWidth-666;
            Box(new Rect(306,112,centerWidth,40),background);
            Label(320,125,350,18,"3D / ОПЕРАЦИОННЫЙ ЦЕНТР",eyebrow);
            if(command!=null)
            {
                if(Button(new Rect(uiWidth-804,118,142,28),"КАРЬЕР",!command.SiteView&&!command.Digital?teal:surface,!command.SiteView&&!command.Digital?background:ink))
                {command.SetDigital(false);command.ShowSite(false);SelectedId="pit";}
                if(Button(new Rect(uiWidth-654,118,142,28),"ЦИФРОВОЙ СЛОЙ",!command.SiteView&&command.Digital?teal:surface,!command.SiteView&&command.Digital?background:ink))
                {bool next=command.SiteView||!command.Digital;command.ShowSite(false);command.SetDigital(next);SelectedId="pit";}
                if(Button(new Rect(uiWidth-504,118,142,28),"ВЕСЬ РУДНИК",command.SiteView?teal:surface,command.SiteView?background:ink))
                {command.ShowSite(true);SelectedId="substation";}
            }
            Label(312,uiHeight-221,centerWidth,25,"ПКМ — вращение   ·   колёсико — масштаб   ·   Home — карьер   ·   H — панели",small);
            float width=(centerWidth-8*6)/9;
            for(int i=0;i<objectIds.Length;i++)
            {
                bool selected=SelectedId==objectIds[i];
                if(Button(new Rect(306+(width+6)*i,uiHeight-178,width,35),objectNames[i],selected?teal:surface,selected?background:ink))
                {Select(objectIds[i]);GUI.FocusControl(null);}
            }
        }

        private void DrawTelemetry()
        {
            var s=data.State;bool valid=HasSnapshot;
            Box(new Rect(16,112,260,230),background);
            Label(34,130,224,18,"ТЕЛЕМЕТРИЯ / ЭНЕРГОСИСТЕМА",eyebrow);
            float grid=valid&&s.gridCapMW>0?s.gridMW/s.gridCapMW*100:0;
            Gauge(new Rect(34,162,100,100),valid?s.bessSoc:0,valid?F(s.bessSoc,"0")+"%":"—",ref batteryGauge,ref lastBattery,teal);
            Gauge(new Rect(158,162,100,100),grid,valid?F(grid,"0")+"%":"—",ref gridGauge,ref lastGrid,sand);
            Label(34,264,100,20,"ЗАРЯД BESS",eyebrow,false,TextAnchor.MiddleCenter);
            Label(158,264,100,20,"СЕТЬ / ЛИМИТ",eyebrow,false,TextAnchor.MiddleCenter);
            Label(34,302,108,22,valid?"ВЭС  "+F(s.windMW)+" МВт":"ВЭС  —",small);
            Label(151,302,108,22,valid?"СЭС  "+F(s.pvMW)+" МВт":"СЭС  —",small);

            Box(new Rect(16,354,260,178),background);
            Label(34,372,224,18,"НАГРУЗКА / ПОСЛЕДНИЕ СНИМКИ",eyebrow);
            Label(34,398,224,30,valid?F(s.loadMW)+" МВт":"—",number);
            var chart=new Rect(34,440,224,59);
            for(int i=0;i<3;i++)Fill(new Rect(chart.x,chart.y+chart.height*i/2,chart.width,1),raised);
            if(powerHistory.Count>1)
            {
                float max=1;foreach(float value in powerHistory)max=Mathf.Max(max,value*1.15f);
                for(int i=1;i<powerHistory.Count;i++)
                {
                    Vector2 a=new Vector2(chart.x+(i-1)*chart.width/17,chart.yMax-powerHistory[i-1]/max*chart.height);
                    Vector2 b=new Vector2(chart.x+i*chart.width/17,chart.yMax-powerHistory[i]/max*chart.height);
                    GuiLine(a,b,teal,1.8f);
                }
            }
            Label(34,508,224,15,"Наблюдения после открытия экрана",TextWithSize(small,10));

            Box(new Rect(16,544,260,uiHeight-682),background);
            Label(34,562,224,18,"ТРАНСПОРТ / СОСТОЯНИЕ",eyebrow);
            int moving=0,charging=0,waiting=0;
            if(valid&&s.trucks!=null)foreach(var truck in s.trucks)
            {if(truck.state=="loaded"||truck.state=="empty")moving++;else if(truck.state=="charging")charging++;else if(truck.state=="waiting")waiting++;}
            Row(34,592,224,"В движении",valid?moving.ToString():"—",teal);
            Row(34,624,224,"На зарядке",valid?charging.ToString():"—",sand);
            Row(34,656,224,"Ожидают",valid?waiting.ToString():"—",orange);
            Label(34,698,224,40,"14 звеньев · по 3 машины\nДвижение по схеме, не GPS",TextWithSize(small,11),true);
        }

        private void Gauge(Rect r,float value,string text,ref Texture2D texture,ref int previous,Color color)
        {
            if(gaugeRing==null)gaugeRing=Arc(100);
            int percent=Mathf.RoundToInt(Mathf.Clamp(value,0,100));
            if(texture==null||previous!=percent)
            {if(texture!=null)Destroy(texture);texture=Arc(percent);previous=percent;}
            var saved=GUI.color;
            GUI.color=MinePlatform.GuiColor(raised);GUI.DrawTexture(r,gaugeRing);
            GUI.color=MinePlatform.GuiColor(color);GUI.DrawTexture(r,texture);GUI.color=saved;
            Label(r.x,r.y+36,r.width,32,text,TextWithSize(number,22),false,TextAnchor.MiddleCenter);
        }
        static Texture2D Arc(int percent)
        {
            var texture=new Texture2D(128,128,TextureFormat.RGBA32,false){hideFlags=HideFlags.HideAndDontSave};
            for(int y=0;y<128;y++)for(int x=0;x<128;x++)
            {
                float dx=x-63.5f,dy=y-63.5f,r=Mathf.Sqrt(dx*dx+dy*dy);
                float angle=Mathf.Repeat(Mathf.Atan2(-dy,dx)*Mathf.Rad2Deg+225,360);
                float alpha=Mathf.Clamp01(2-Mathf.Abs(r-53));
                texture.SetPixel(x,y,new Color(1,1,1,angle<=percent*2.7f?alpha:0));
            }
            texture.Apply();return texture;
        }
        static void GuiLine(Vector2 a,Vector2 b,Color color,float width)
        {
            var matrix=GUI.matrix;var d=b-a;
            GUI.matrix=matrix*Matrix4x4.TRS(new Vector3(a.x,a.y,0),Quaternion.Euler(0,0,Mathf.Atan2(d.y,d.x)*Mathf.Rad2Deg),Vector3.one);
            Fill(new Rect(0,-width*.5f,d.magnitude,width),color);GUI.matrix=matrix;
        }
        private void DrawTruckLabels(float scale)
        {
            truckLabelRects.Clear();
            if(command==null||command.SiteView||!HasSnapshot||data.State.trucks==null)return;
            foreach(int i in new[]{0,5,10})
            {
                if(i>=command.trucks.Length||!command.trucks[i].gameObject.activeSelf)continue;
                var point=cameraRig.GetComponent<Camera>().WorldToScreenPoint(command.trucks[i].position+Vector3.up*4);
                if(point.z<=0)continue;
                var rect=new Rect(point.x/scale-58,(Screen.height-point.y)/scale-48,116,42);
                if(rect.x<306||rect.xMax>uiWidth-356||rect.y<163||rect.yMax>uiHeight-240)continue;
                bool overlap=false;foreach(var other in truckLabelRects)if(other.Overlaps(rect)){overlap=true;break;}
                if(overlap)continue;truckLabelRects.Add(rect);
                var truck=data.State.trucks[i];
                string text="T"+(i+1).ToString("00")+"  ·  "+F(truck.soc,"0")+"%\n"+TruckStateName(truck.state);
                if(Button(rect,text,background,truck.state=="waiting"?orange:teal))Select("truck-"+(i+1).ToString("00"));
            }
        }
        static string TruckStateName(string state)
        {
            switch(state){case "loaded":return "С РУДОЙ";case "empty":return "ПОРОЖНИЙ";case "charging":return "ЗАРЯДКА";case "waiting":return "ОЖИДАНИЕ";default:return "—";}
        }

        private void DrawInspector()
        {
            var s = data.State;
            float x = uiWidth - 328f, y = 112f, w = 312f;
            float h = uiHeight - 250f;
            Box(new Rect(x, y, w, h), background);
            Label(x + 20, y + 17, w - 40, 16, "ВЫБРАННЫЙ ОБЪЕКТ", eyebrow);
            Label(x + 20, y + 42, w - 40, 29, ObjectName(SelectedId), TextWithSize(title, 23));
            Fill(new Rect(x + 20, y + 84, w - 40, 1), raised);
            DrawSelectedDetails(x + 20, y + 100, w - 40);

            float lineY = y + 315;
            Fill(new Rect(x + 20, lineY, w - 40, 1), raised);
            Label(x + 20, lineY + 15, w - 40, 17, "РЕШЕНИЕ ДИСПЕТЧЕРА", eyebrow);
            Label(x + 20, lineY + 40, w - 40, 28, HasSnapshot ? s.mode ?? "—" : "Ожидание LIVE", TextWithColor(body, teal), true);
            Label(x + 20, lineY + 73, w - 40, 62, HasSnapshot ? s.why ?? "" :
                "После получения корректного снимка здесь появится решение диспетчера.", small, true);
            float connectY = y + h - 187;
            Fill(new Rect(x + 20, connectY - 12, w - 40, 1), raised);
            Label(x + 20, connectY, w - 40, 17, "ИСТОЧНИК ДАННЫХ", eyebrow);
            Label(x + 20, connectY + 25, w - 40, 29,
                data.LiveMode ? "LIVE / " + (!HasSnapshot ? "ожидание первого снимка" :
                data.IsStale ? "нет свежих данных" : data.IsConnected ? "подключено" : "ожидание") :
                "ДЕМО / иллюстративная модель",
                TextWithColor(small, data.LiveMode && data.IsStale ? orange : muted), true);
            GUI.SetNextControlName("tynys-endpoint");
            Color saved = GUI.backgroundColor;
            GUI.backgroundColor = MinePlatform.GuiColor(raised);
            endpoint = GUI.TextField(new Rect(x + 20, connectY + 58, w - 40, 31), endpoint, field);
            GUI.backgroundColor = saved;
            if (Button(new Rect(x + 20, connectY + 98, w - 40, 32),
                data.LiveMode ? "ВКЛЮЧИТЬ ДЕМО · ИЛЛЮСТРАЦИЯ" : "ВЕРНУТЬСЯ В LIVE", data.LiveMode ? raised : teal,
                data.LiveMode ? ink : background))
            {
                data.Endpoint = endpoint.Trim();
                data.SetLive(!data.LiveMode);
                GUI.FocusControl(null);
            }
            Label(x + 20, connectY + 140, w - 40, 35,
                string.IsNullOrEmpty(data.Status) ? "JSON endpoint из веб-проекта" : data.Status, small, true);
        }

        private void DrawSelectedDetails(float x, float y, float w)
        {
            if (!HasSnapshot)
            {
                Chip(new Rect(x, y, w, 28), "ДАННЫЕ ЕЩЁ НЕ ПОЛУЧЕНЫ", orange);
                Label(x, y + 48, w, 104,
                    "Ожидаем API проекта; подключение повторяется автоматически. Показатели пока не известны. Иллюстративное демо включается отдельно кнопкой ниже.",
                    small, true);
                return;
            }
            var s = data.State;
            if(SelectedId.StartsWith("truck-")&&int.TryParse(SelectedId.Substring(6),out int truckIndex)&&truckIndex>=1&&truckIndex<=s.trucks.Length)
            {
                var truck=s.trucks[truckIndex-1];
                Chip(new Rect(x,y,w,28),TruckStateName(truck.state),truck.state=="waiting"?orange:teal);
                Progress(x,y+46,w,truck.soc,"Заряд батареи",teal);
                Label(x,y+104,w,82,"Одно визуальное звено соответствует трём электросамосвалам. Положение на дороге иллюстративное; состояние и заряд — из модели.",small,true);
                return;
            }
            switch (SelectedId)
            {
                case "pit":
                    Row(x, y, w, "Подача в переработку", F(s.feedTPH, "0") + " т/ч");
                    Row(x, y + 35, w, "Выход меди", F(s.cuTPH) + " т/ч", sand);
                    Label(x, y + 87, w, 78, "Самосвалы показывают движение руды от карьера к складам. Два типа сырья питают обогатительные линии.", small, true);
                    break;
                case "pile-soft":
                    Row(x, y, w, "Запас мягкой руды", F(s.pileSoftTonnes, "0") + " т", sand);
                    Progress(x, y + 48, w, s.pileSoftPct, "Заполнение", sand);
                    Label(x, y + 98, w, 80, "Буфер сырья позволяет менять темп переработки в течение суток и учитывать доступность энергии.", small, true);
                    break;
                case "pile-hard":
                    Row(x, y, w, "Запас твёрдой руды", F(s.pileHardTonnes, "0") + " т", sand);
                    Progress(x, y + 48, w, s.pileHardPct, "Заполнение", sand);
                    Label(x, y + 98, w, 80, "Твёрдая руда увеличивает нагрузку на измельчение. Смешивание сырья связывает энергетику и выпуск меди.", small, true);
                    break;
                case "line-1":
                case "line-2":
                    bool first = SelectedId == "line-1";
                    bool available = first ? s.line1Available : s.line2Available;
                    Chip(new Rect(x, y, w, 28), available ? "В РАБОТЕ" : "ЛИНИЯ ОСТАНОВЛЕНА", available ? teal : orange);
                    Row(x, y + 48, w, "Подача", F(first ? s.line1Feed : s.line2Feed, "0") + " т/ч");
                    Row(x, y + 84, w, "P80", F(s.p80, "0") + " мкм");
                    Label(x, y + 128, w, 60, "Цвет и движение потока отражают доступность линии. P80 — общий показатель крупности продукта.", small, true);
                    break;
                case "wind":
                    Row(x, y, w, "Выработка ВЭС", F(s.windMW) + " МВт", teal);
                    Row(x, y + 35, w, "Доля всех ВИЭ", Percent(s.renewShare));
                    Label(x, y + 87, w, 86, "Ветровая генерация меняется во времени. Диспетчер согласует потребление, запас руды и доступную мощность сети.", small, true);
                    break;
                case "pv":
                    Row(x, y, w, "Выработка СЭС", F(s.pvMW) + " МВт", teal);
                    Row(x, y + 35, w, "Солнечное время", F(s.hour, "00.0") + " ч");
                    Label(x, y + 87, w, 80, "Солнечная генерация следует суточному профилю. Избыток энергии можно направить в BESS или переработку.", small, true);
                    break;
                case "bess":
                    Chip(new Rect(x, y, w, 28), s.bessAvailable ? "НАКОПИТЕЛЬ ДОСТУПЕН" : "НАКОПИТЕЛЬ НЕДОСТУПЕН", s.bessAvailable ? teal : orange);
                    Progress(x, y + 45, w, s.bessSoc, "Заряд / SoC", teal);
                    Row(x, y + 95, w, s.bessMW > 0.01f ? "Разряд накопителя" :
                        s.bessMW < -0.01f ? "Заряд накопителя" : "Мощность BESS",
                        F(Mathf.Abs(s.bessMW)) + " МВт", teal);
                    Label(x, y + 139, w, 56, "Накопитель сглаживает изменения доступной генерации и помогает удерживать лимит сети.", small, true);
                    break;
                default:
                    Row(x, y, w, "Импорт из сети", F(s.gridMW) + " МВт", sand);
                    Row(x, y + 35, w, "Лимит KEGOC", F(s.gridCapMW) + " МВт");
                    if (data.LiveMode)
                    {
                        Row(x, y + 70, w, "Гибкость нагрузки", F(s.flexMW) + " МВт", teal);
                        Row(x, y + 105, w, "Горизонт гибкости", F(s.flexHours) + " ч");
                        Label(x, y + 153, w, 42, "Медь, т: V0 " + F(s.cuV0) + "  ·  V1 " + F(s.cuV1) + "  ·  V2 " + F(s.cuV2), small, true);
                    }
                    else
                        Label(x, y + 89, w, 95, "Резерв гибкости и сравнение V0 / V1 / V2 доступны с данными LIVE. Демо иллюстрирует контур и не является расчётом ТЭО.", small, true);
                    break;
            }
        }

        private void DrawScenarios()
        {
            float y = uiHeight - 118;
            Box(new Rect(16, y, uiWidth - 32, 102), background);
            Label(34, y + 13, 310, 17, data.LiveMode ? "LIVE / УПРАВЛЕНИЕ В ВЕБ-ПАНЕЛИ" : "СЦЕНАРИИ ДЕМОНСТРАЦИИ", eyebrow);
            Label(352, y + 12, uiWidth - 820, 18,
                data.LiveMode ? "События задаются в существующей веб-панели проекта." :
                "Демонстрационные значения • выбор события меняет работу контура", small);

            bool wasEnabled = GUI.enabled;
            GUI.enabled = !data.LiveMode;
            float resetW = 78f, pauseW = 92f, speedW = 58f, rightMargin = 34f, gap = 7f;
            float controlsWidth = resetW + pauseW + speedW + gap * 3f;
            float eventsWidth = uiWidth - 68f - controlsWidth - 12f;
            float eventW = (eventsWidth - gap * 6f) / 7f;
            for (int i = 0; i < events.Length; i++)
            {
                bool current = data.Scenario == events[i] && !data.LiveMode;
                if (Button(new Rect(34f + (eventW + gap) * i, y + 43, eventW, 40),
                    eventNames[i], current ? sand : surface, current ? background : ink))
                {
                    data.SetScenario(events[i]);
                    GUI.FocusControl(null);
                }
            }
            float cx = uiWidth - rightMargin - controlsWidth;
            if (Button(new Rect(cx, y + 43, resetW, 40), "СБРОС", raised, ink))
            {
                data.ResetDemo();
                fast = false;
                data.SecondsPerHour = 10f;
                GUI.FocusControl(null);
            }
            cx += resetW + gap;
            if (Button(new Rect(cx, y + 43, pauseW, 40), data.Paused ? "ПУСК" : "ПАУЗА", raised, ink))
            {
                data.Paused = !data.Paused;
                GUI.FocusControl(null);
            }
            cx += pauseW + gap;
            if (Button(new Rect(cx, y + 43, speedW, 40), fast ? "4×" : "1×", raised, teal))
            {
                fast = !fast;
                data.SecondsPerHour = fast ? 2.5f : 10f;
                GUI.FocusControl(null);
            }
            GUI.enabled = wasEnabled;
            Label(uiWidth - 270, y + 12, 235, 18, "ПРОТОТИП КОНЦЕПЦИИ / OpenEgiz", eyebrow, false, TextAnchor.MiddleRight);
        }

        private void Row(float x, float y, float w, string key, string value, Color? accent = null)
        {
            Label(x, y + 3, w * 0.64f, 25, key, small);
            Label(x + w * 0.53f, y, w * 0.47f, 28, value,
                TextWithColor(body, accent ?? ink), false, TextAnchor.MiddleRight);
        }

        private void Progress(float x, float y, float w, float value, string caption, Color accent)
        {
            float pct = Normalized(value);
            Label(x, y, w * 0.7f, 22, caption, small);
            Label(x + w * 0.7f, y, w * 0.3f, 22, F(pct * 100f, "0") + "%", body, false, TextAnchor.MiddleRight);
            Box(new Rect(x, y + 29, w, 7), raised);
            if (pct > 0f) Box(new Rect(x, y + 29, Mathf.Max(5f, w * pct), 7), accent);
        }

        private void Chip(Rect r, string text, Color color)
        {
            Box(r, new Color(color.r * 0.18f, color.g * 0.18f, color.b * 0.18f, 1f));
            Label(r.x + 6, r.y, r.width - 12, r.height, text, TextWithColor(badge, color));
        }

        private bool Button(Rect r, string text, Color fill, Color foreground)
        {
            Color saved = GUI.backgroundColor;
            GUI.backgroundColor = MinePlatform.GuiColor(fill);
            var style = new GUIStyle(button);
            style.normal.textColor = foreground;
            style.hover.textColor = foreground;
            style.active.textColor = foreground;
            bool clicked = GUI.Button(r, text, style);
            GUI.backgroundColor = saved;
            return clicked;
        }

        private void Label(float x, float y, float width, float height, string text,
            GUIStyle style, bool wrap = false, TextAnchor alignment = TextAnchor.UpperLeft)
        {
            GUIStyle use = new GUIStyle(style) { wordWrap = wrap };
            if (alignment != TextAnchor.UpperLeft) use.alignment = alignment;
            GUI.Label(new Rect(x, y, width, height), text ?? "", use);
        }

        private void Box(Rect r, Color color, float alpha = 1f)
        {
            Color saved = GUI.color;
            GUI.color = MinePlatform.GuiColor(new Color(color.r, color.g, color.b, alpha));
            GUI.Box(r, GUIContent.none, panel);
            GUI.color = saved;
            if(r.height>=25&&r.width>=70)
            {
                var edge=Hex(0x294650);edge.a=alpha;
                Fill(new Rect(r.x+2,r.y,r.width-4,1),edge);
                Fill(new Rect(r.x+2,r.yMax-1,r.width-4,1),edge);
                Fill(new Rect(r.x,r.y+2,1,r.height-4),edge);
                Fill(new Rect(r.xMax-1,r.y+2,1,r.height-4),edge);
                if(r.width>300&&r.height>70)
                {
                    Fill(new Rect(r.x,r.y,18,2),teal);
                    Fill(new Rect(r.xMax-18,r.yMax-2,18,2),teal);
                }
            }
        }

        private static void Fill(Rect r, Color color)
        {
            Color saved = GUI.color;
            GUI.color = MinePlatform.GuiColor(color);
            GUI.DrawTexture(r, Texture2D.whiteTexture);
            GUI.color = saved;
        }

        private void Dot(float x, float y, Color color) { Box(new Rect(x - 4, y - 4, 8, 8), color); }
        private static GUIStyle TextWithColor(GUIStyle original, Color color)
        {
            var style = new GUIStyle(original);
            style.normal.textColor = color;
            return style;
        }
        private static GUIStyle TextWithSize(GUIStyle original, int size)
        {
            return new GUIStyle(original) { fontSize = size };
        }
        private static string ObjectName(string id)
        {
            if(id.StartsWith("truck-"))return "Самосвал / звено "+id.Substring(6);
            switch (id)
            {
                case "pit": return "Открытый карьер";
                case "pile-soft": return "Склад мягкой руды";
                case "pile-hard": return "Склад твёрдой руды";
                case "line-1": return "Переработка / линия 1";
                case "line-2": return "Переработка / линия 2";
                case "wind": return "Ветровая станция";
                case "pv": return "Солнечная станция";
                case "bess": return "Накопитель BESS";
                default: return "Подстанция / сеть";
            }
        }
        private static float Normalized(float value) { return Mathf.Clamp01(value / 100f); }
        private static string Percent(float value) { return F(Normalized(value) * 100f, "0") + "%"; }
        private static string F(float value, string format = "0.0") { return value.ToString(format, CultureInfo.InvariantCulture); }
        private static Color Hex(uint rgb)
        {
            return new Color(((rgb >> 16) & 255) / 255f, ((rgb >> 8) & 255) / 255f, (rgb & 255) / 255f, 1f);
        }
        private void OnDestroy()
        {
            IsTyping = false;
            if (rounded != null) Destroy(rounded);
            if(gaugeRing!=null)Destroy(gaugeRing);
            if(batteryGauge!=null)Destroy(batteryGauge);
            if(gridGauge!=null)Destroy(gridGauge);
        }
    }
}
