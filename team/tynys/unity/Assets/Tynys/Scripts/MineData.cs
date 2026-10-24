using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace Tynys
{
    public enum DemoScenario { Normal, Lull, LineTrip, Kegoc, HardOre, PlanUp, BessFault }

    [Serializable]
    public class TruckState
    {
        public string state;
        public float soc, routePos;
    }

    [Serializable]
    public class MineState
    {
        public float hour, windMW, pvMW, gridMW, gridCapMW, loadMW, renewShare;
        public float pileSoftPct, pileHardPct, pileSoftTonnes, pileHardTonnes;
        public float bessSoc, bessMW, chargeMW, feedTPH, p80, cuTPH, flexMW, flexHours;
        public float cuV0, cuV1, cuV2, line1Feed, line2Feed;
        public bool line1Available = true, line2Available = true, bessAvailable = true;
        public string mode, why, simTime;
        public TruckState[] trucks;
    }

    /// <summary>
    /// Display data only. Demo values illustrate behaviour; they are not MPC
    /// results or a simulation of mine economics. Live mode reads Eclipse Ditto
    /// through the existing tynys-ui proxy and never writes twin properties.
    /// </summary>
    public class MineData : MonoBehaviour
    {
        public MineState State { get; private set; }
        public bool LiveMode = true;
        public bool IsConnected, IsStale;
        public string Endpoint = "http://localhost:8095/ditto/api/2/";
        public string Status;
        public float SecondsPerHour = 10;
        public bool Paused;
        public DemoScenario Scenario;
        public bool CanSetScenario { get { return !LiveMode; } }
        public bool HasSnapshot { get { return !LiveMode || lastLive != null; } }
        public int SnapshotCount { get; private set; }

        private static readonly string[] Names = {
            "site", "plant", "energy", "coordinator", "shadow-v0", "shadow-v1",
            "pile-soft", "pile-hard", "line-1", "line-2", "wind", "pv", "bess", "substation",
            "truck-01", "truck-02", "truck-03", "truck-04", "truck-05", "truck-06", "truck-07",
            "truck-08", "truck-09", "truck-10", "truck-11", "truck-12", "truck-13", "truck-14"
        };
        private Coroutine polling;
        private UnityWebRequest pending;
        private MineState lastLive;
        private bool appliedLive;
        private float demoHour = 9f, lastReceived, lastDemoHour = 9f;
        private float demoBessMWh = 72;
        private const float StaleAfterSeconds = 5;
        private const float MaxPayloadBytes = 1024 * 1024;

        private void Awake()
        {
            State = EmptyState();
#if UNITY_WEBGL && !UNITY_EDITOR
            Endpoint = "/ditto/api/2/";
#else
            var args = Environment.GetCommandLineArgs();
            // Offline illustration and verification are deliberate opt-ins.
            if (Array.IndexOf(args, "--tynys-demo") >= 0 || Array.IndexOf(args, "--tynys-verify") >= 0)
                LiveMode = false;
            int apiArg = Array.IndexOf(args, "--tynys-api");
            if (apiArg >= 0 && apiArg + 1 < args.Length) Endpoint = args[apiArg + 1];
#endif
        }

        private void OnEnable()
        {
            ApplyMode();
        }

        private void OnDisable()
        {
            StopPolling();
        }

        private void Update()
        {
            if (LiveMode != appliedLive) ApplyMode();
            if (LiveMode)
            {
                if (IsConnected && Time.realtimeSinceStartup - lastReceived > StaleAfterSeconds)
                {
                    IsStale = true;
                    Status = "DITTO: данные устарели; показан последний снимок.";
                }
                return;
            }
            if (!Paused)
            {
                demoHour += Time.unscaledDeltaTime / Mathf.Max(0.1f, SecondsPerHour);
                UpdateDemo();
            }
        }

        public void SetLive(bool live)
        {
            if (LiveMode == live && appliedLive == live && State != null) return;
            LiveMode = live;
            ApplyMode();
        }

        public void SetScenario(DemoScenario scenario)
        {
            if (LiveMode) return;
            Scenario = scenario;
            UpdateDemo();
        }

        public void ResetDemo()
        {
            if (LiveMode) return;
            demoHour = 9f;
            lastDemoHour = 9f;
            demoBessMWh = 72;
            Scenario = DemoScenario.Normal;
            Paused = false;
            UpdateDemo();
        }

        private void ApplyMode()
        {
            StopPolling();
            appliedLive = LiveMode;
            Paused = false;
            IsConnected = false;
            IsStale = LiveMode;
            if (LiveMode)
            {
                // A demo frame must never become a purported live snapshot.
                State = lastLive ?? EmptyState();
                Status = lastLive == null
                    ? "DITTO: ожидаем первый снимок."
                    : "DITTO: подключение; показан предыдущий снимок.";
                if (isActiveAndEnabled) polling = StartCoroutine(Poll());
            }
            else
            {
                lastDemoHour = demoHour;
                State = EmptyState();
                UpdateDemo();
            }
        }

        private void StopPolling()
        {
            if (pending != null)
            {
                pending.Abort();
                pending.Dispose();
                pending = null;
            }
            if (polling != null)
            {
                StopCoroutine(polling);
                polling = null;
            }
        }

        private IEnumerator Poll()
        {
            while (LiveMode)
            {
                Uri baseUri;
                string baseUrl = (Endpoint ?? "").Trim().TrimEnd('/') + "/";
                if (baseUrl.StartsWith("/") && Uri.TryCreate(Application.absoluteURL, UriKind.Absolute, out var pageUri))
                    baseUrl = new Uri(pageUri, baseUrl).AbsoluteUri;
                if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out baseUri) ||
                    (baseUri.Scheme != "http" && baseUri.Scheme != "https"))
                {
                    MarkFailure("некорректный адрес API");
                    yield return new WaitForSecondsRealtime(1);
                    continue;
                }
                StringBuilder ids = new StringBuilder();
                for (int i = 0; i < Names.Length; i++)
                {
                    if (i > 0) ids.Append(',');
                    ids.Append("kz.tynys:").Append(Names[i]);
                }
                string url = baseUrl + "things?ids=" + Uri.EscapeDataString(ids.ToString()) +
                             "&fields=thingId%2Cfeatures";
                pending = UnityWebRequest.Get(url);
                pending.timeout = 5;
                pending.SetRequestHeader("Accept", "application/json");
                yield return pending.SendWebRequest();
                if (!LiveMode) yield break;

                if (pending.result != UnityWebRequest.Result.Success)
                {
                    string message = pending.responseCode > 0
                        ? "HTTP " + pending.responseCode
                        : "сеть недоступна";
                    MarkFailure(message);
                }
                else if (pending.downloadedBytes > MaxPayloadBytes)
                {
                    MarkFailure("слишком большой ответ API");
                }
                else
                {
                    MineState snapshot;
                    string error;
                    if (TryParseSnapshot(pending.downloadHandler.text, out snapshot, out error))
                    {
                        State = snapshot;
                        lastLive = snapshot;
                        lastReceived = Time.realtimeSinceStartup;
                        IsConnected = true;
                        IsStale = false;
                        SnapshotCount++;
                        Status = "DITTO · данные платформы · только чтение";
                    }
                    else MarkFailure(error);
                }
                pending.Dispose();
                pending = null;
                yield return new WaitForSecondsRealtime(1);
            }
        }

        private void MarkFailure(string reason)
        {
            IsConnected = false;
            IsStale = true;
            Status = "DITTO: " + reason + (lastLive == null
                ? ". Данных пока нет."
                : ". Показан последний снимок.");
        }

        private static MineState EmptyState()
        {
            MineState s = new MineState {
                mode = "—", why = "Ожидание данных.", simTime = "—",
                line1Available = false, line2Available = false, bessAvailable = false,
                trucks = new TruckState[14]
            };
            for (int i = 0; i < s.trucks.Length; i++)
                s.trucks[i] = new TruckState { state = "unknown" };
            return s;
        }

        private void UpdateDemo()
        {
            if (State == null) State = EmptyState();
            MineState s = State;
            float elapsedHours = Mathf.Max(0, demoHour - lastDemoHour);
            lastDemoHour = demoHour;
            s.hour = demoHour;
            float daylight = Mathf.Max(0, Mathf.Sin((Mathf.Repeat(demoHour, 24) - 6) / 12 * Mathf.PI));
            s.windMW = Mathf.Clamp(165 + 95 * Mathf.Sin(demoHour * 0.29f), 0, 300);
            if (Scenario == DemoScenario.Lull) s.windMW *= 0.08f;
            s.pvMW = 230 * daylight;
            s.gridCapMW = Scenario == DemoScenario.Kegoc ? 180 : 260;
            s.line1Available = true;
            s.line2Available = Scenario != DemoScenario.LineTrip;
            s.bessAvailable = Scenario != DemoScenario.BessFault;
            float renew = s.windMW + s.pvMW;
            bool inhale = renew > 180;
            float feed = inhale ? 3550 : 2800;
            if (Scenario == DemoScenario.HardOre) feed *= 0.83f;
            if (Scenario == DemoScenario.PlanUp) feed *= 1.1f;
            s.line1Feed = Mathf.Min(4000, feed);
            s.line2Feed = s.line2Available ? s.line1Feed : 0;
            s.chargeMW = inhale ? 54 : 0;
            s.feedTPH = s.line1Feed + s.line2Feed;
            s.loadMW = 100 + s.feedTPH * 0.018f + s.chargeMW;
            // Illustrative energy balance, with the repository's 60 MW / 120 MWh
            // BESS scale and 10–95% operating window. Positive power discharges.
            float powerInterval = Mathf.Max(elapsedHours, 0.0001f);
            float maxDischarge = Mathf.Min(60, Mathf.Max(0, demoBessMWh - 12) / powerInterval);
            float maxCharge = Mathf.Min(60, Mathf.Max(0, 114 - demoBessMWh) / powerInterval);
            s.bessMW = s.bessAvailable ? Mathf.Clamp(s.loadMW - renew, -maxCharge, maxDischarge) : 0;
            float shortage = Mathf.Max(0, s.loadMW - renew - s.bessMW - s.gridCapMW);
            if (shortage > 0)
            {
                float reducedCharge = Mathf.Min(s.chargeMW, shortage);
                s.chargeMW -= reducedCharge;
                shortage -= reducedCharge;
                float availableFeed = Mathf.Max(0, s.feedTPH - shortage / 0.018f);
                float ratio = s.feedTPH > 0 ? availableFeed / s.feedTPH : 0;
                s.line1Feed *= ratio;
                s.line2Feed *= ratio;
                s.feedTPH = availableFeed;
                s.loadMW = 100 + s.feedTPH * 0.018f + s.chargeMW;
            }
            s.gridMW = Mathf.Clamp(s.loadMW - renew - s.bessMW, 0, s.gridCapMW);
            s.renewShare = 100 * Mathf.Clamp01(renew / Mathf.Max(1, s.loadMW + Mathf.Max(0, -s.bessMW)));
            s.pileSoftPct = Mathf.Clamp(52 + 14 * Mathf.Sin(demoHour * 0.13f), 0, 100);
            s.pileHardPct = Mathf.Clamp(49 - 12 * Mathf.Sin(demoHour * 0.13f) +
                                        (Scenario == DemoScenario.HardOre ? 22 : 0), 0, 100);
            s.pileSoftTonnes = s.pileSoftPct * 2000;
            s.pileHardTonnes = s.pileHardPct * 2000;
            demoBessMWh = Mathf.Clamp(demoBessMWh - s.bessMW * elapsedHours, 12, 114);
            s.bessSoc = 100 * demoBessMWh / 120;
            s.p80 = inhale ? 120 : 200;
            // An illustrative process readout, not a production forecast.
            s.cuTPH = s.feedTPH * 0.0043f * 0.879f;
            s.flexMW = 0;
            s.flexHours = 0;
            s.cuV0 = s.cuV1 = s.cuV2 = 0; // No fabricated comparative evidence.
            s.mode = inhale ? "вдох" : "выдох";
            s.simTime = "Демо · " + Mathf.FloorToInt(Mathf.Repeat(demoHour, 24)).ToString("00", CultureInfo.InvariantCulture) + ":" + Mathf.FloorToInt(Mathf.Repeat(demoHour * 60, 60)).ToString("00", CultureInfo.InvariantCulture);
            string detail;
            switch (Scenario)
            {
                case DemoScenario.Lull: detail = "Штиль: ветер снижен до 8 %."; break;
                case DemoScenario.LineTrip: detail = "Линия 2 отключена."; break;
                case DemoScenario.Kegoc: detail = "Ограничение KEGOC: предел сети 180 МВт (−80 МВт)."; break;
                case DemoScenario.HardOre: detail = "Твёрдая руда: больше запас на складе, ниже подача."; break;
                case DemoScenario.PlanUp: detail = "Иллюстрация повышения подачи на 10 %."; break;
                case DemoScenario.BessFault: detail = "Накопитель недоступен."; break;
                default: detail = inhale ? "Много ВИЭ: выше подача и идёт зарядка." : "Меньше ВИЭ: ниже подача, зарядка отложена."; break;
            }
            s.why = "Иллюстративный режим, без расчёта MPC. " + detail;
            int charging = Mathf.RoundToInt(s.chargeMW / 18);
            for (int i = 0; i < s.trucks.Length; i++)
            {
                float phase = Mathf.Repeat(demoHour * .22f + i / 14f, 1);
                s.trucks[i].routePos = phase;
                s.trucks[i].soc = Mathf.Clamp(58 + 18 * Mathf.Sin(demoHour * 0.21f + i), 10, 95);
                s.trucks[i].state = i < charging ? "charging" : phase < 0.5f ? "loaded" : "empty";
            }
            IsConnected = false;
            IsStale = false;
            Status = "ДЕМО · иллюстрация · не результат MPC";
        }

        /// <summary>
        /// Parses an actual Ditto GET /things array. The candidate snapshot is
        /// returned only after essential twins, fields and types are validated.
        /// Missing initial telemetry is an error, not a synthetic zero reading.
        /// Unknown extra twins/features are ignored for forward compatibility.
        /// </summary>
        public static bool TryParseSnapshot(string json, out MineState snapshot, out string error)
        {
            snapshot = null;
            error = null;
            try
            {
                if (string.IsNullOrWhiteSpace(json) || json.Length > MaxPayloadBytes)
                    throw new FormatException("пустой или слишком большой ответ");
                List<object> array = new JsonReader(json).Read() as List<object>;
                if (array == null || array.Count == 0) throw new FormatException("ожидался непустой массив двойников");
                Dictionary<string, Dictionary<string, object>> twins = new Dictionary<string, Dictionary<string, object>>();
                foreach (object item in array)
                {
                    Dictionary<string, object> thing = Obj(item, "thing");
                    string id = Required(thing, "thingId") as string;
                    if (id == null) throw new FormatException("thingId должен быть строкой");
                    if (!id.StartsWith("kz.tynys:", StringComparison.Ordinal)) continue;
                    string name = id.Substring("kz.tynys:".Length);
                    if (twins.ContainsKey(name)) throw new FormatException("повторный двойник: " + name);
                    twins.Add(name, Obj(Required(thing, "features"), name + ".features"));
                }
                SnapshotFields f = new SnapshotFields(twins);
                MineState s = EmptyState();
                s.hour = f.Number("site", "sim_hour");
                s.simTime = f.Text("site", "sim_time");
                s.windMW = f.Number("wind", "power_mw");
                s.pvMW = f.Number("pv", "power_mw");
                s.gridMW = f.Number("substation", "grid_mw");
                s.gridCapMW = f.Number("substation", "grid_cap_mw");
                s.loadMW = f.Number("energy", "load_mw");
                s.renewShare = f.Number("energy", "renew_share_pct");
                s.chargeMW = f.Number("energy", "charge_mw");
                s.pileSoftPct = f.Percent("pile-soft", "fill_pct");
                s.pileHardPct = f.Percent("pile-hard", "fill_pct");
                s.pileSoftTonnes = f.Number("pile-soft", "tonnes");
                s.pileHardTonnes = f.Number("pile-hard", "tonnes");
                s.bessSoc = f.Percent("bess", "soc");
                s.bessMW = f.SignedNumber("bess", "power_mw");
                s.bessAvailable = f.Boolean("bess", "available");
                s.feedTPH = f.Number("plant", "feed_tph");
                s.p80 = f.Number("plant", "p80_um");
                s.cuTPH = f.Number("plant", "cu_tph");
                s.line1Feed = f.Number("line-1", "feed_tph");
                s.line2Feed = f.Number("line-2", "feed_tph");
                s.line1Available = f.Boolean("line-1", "available");
                s.line2Available = f.Boolean("line-2", "available");
                s.flexMW = f.Number("substation", "flex_down_mw");
                s.flexHours = f.Number("substation", "flex_down_h");
                s.cuV0 = f.Number("shadow-v0", "cu_t");
                s.cuV1 = f.Number("shadow-v1", "cu_t");
                s.cuV2 = f.Number("site", "cu_t");
                s.mode = f.Text("coordinator", "mode");
                s.why = f.Text("coordinator", "why");
                for (int i = 0; i < 14; i++)
                {
                    string name = "truck-" + (i + 1).ToString("00", CultureInfo.InvariantCulture);
                    TruckState t = s.trucks[i];
                    t.state = f.Text(name, "state");
                    // Exact states published by tynys/fleet.py::group_view.
                    if (t.state != "charging" && t.state != "waiting" && t.state != "loaded" && t.state != "empty")
                        throw new FormatException(name + ".state неизвестно");
                    t.soc = f.Percent(name, "soc");
                    t.routePos = f.Number(name, "route_pos");
                    if (t.routePos > 1) throw new FormatException(name + ".route_pos вне 0–1");
                }
                snapshot = s;
                return true;
            }
            catch (FormatException ex)
            {
                error = "неверный снимок: " + ex.Message;
                return false;
            }
            catch (Exception)
            {
                error = "неверный снимок: ошибка разбора";
                return false;
            }
        }

        private static object Required(Dictionary<string, object> obj, string key)
        {
            object value;
            if (!obj.TryGetValue(key, out value) || value == null)
                throw new FormatException("нет поля " + key);
            return value;
        }

        private static Dictionary<string, object> Obj(object value, string path)
        {
            Dictionary<string, object> obj = value as Dictionary<string, object>;
            if (obj == null) throw new FormatException(path + " должен быть объектом");
            return obj;
        }

        private sealed class SnapshotFields
        {
            private readonly Dictionary<string, Dictionary<string, object>> twins;
            public SnapshotFields(Dictionary<string, Dictionary<string, object>> source) { twins = source; }
            private object Value(string name, string field)
            {
                Dictionary<string, object> features;
                if (!twins.TryGetValue(name, out features)) throw new FormatException("нет двойника " + name);
                string path = name + "." + field;
                object feature;
                if (!features.TryGetValue(field, out feature)) throw new FormatException("нет поля " + path);
                return Required(Obj(Required(Obj(feature, path), "properties"), path + ".properties"), "value");
            }
            public float Number(string name, string field)
            {
                float n = SignedNumber(name, field);
                if (n < 0) throw new FormatException(name + "." + field + " вне диапазона");
                return n;
            }
            public float SignedNumber(string name, string field)
            {
                object raw = Value(name, field);
                if (!(raw is double)) throw new FormatException(name + "." + field + " должно быть числом");
                double n = (double)raw;
                if (n < -float.MaxValue || n > float.MaxValue) throw new FormatException(name + "." + field + " вне диапазона");
                return (float)n;
            }
            public float Percent(string name, string field)
            {
                float n = Number(name, field);
                if (n > 100.01f) throw new FormatException(name + "." + field + " вне 0–100");
                return Mathf.Clamp(n, 0, 100);
            }
            public string Text(string name, string field)
            {
                string value = Value(name, field) as string;
                if (value == null) throw new FormatException(name + "." + field + " должно быть строкой");
                return value;
            }
            public bool Boolean(string name, string field)
            {
                object value = Value(name, field);
                if (!(value is bool)) throw new FormatException(name + "." + field + " должно быть boolean");
                return (bool)value;
            }
        }

        // Small strict JSON reader. No dependency on packages or JsonUtility's
        // silent defaults for missing fields. Supports nested properties and
        // JSON strings such as coordinator.plan_json without interpreting them.
        private sealed class JsonReader
        {
            private readonly string source;
            private int at;
            public JsonReader(string json) { source = json; }
            public object Read()
            {
                object value = Value(0);
                Space();
                if (at != source.Length) Fail();
                return value;
            }
            private void Space()
            {
                while (at < source.Length && (source[at] == ' ' || source[at] == '\n' ||
                    source[at] == '\r' || source[at] == '\t')) at++;
            }
            private bool Eat(char c)
            {
                Space();
                if (at < source.Length && source[at] == c) { at++; return true; }
                return false;
            }
            private void Need(char c) { if (!Eat(c)) Fail(); }
            private void Fail() { throw new FormatException("повреждён JSON (позиция " + at + ")"); }
            private object Value(int depth)
            {
                Space();
                if (depth > 32 || at >= source.Length) { Fail(); return null; }
                char c = source[at];
                if (c == '{')
                {
                    at++;
                    Dictionary<string, object> obj = new Dictionary<string, object>();
                    if (Eat('}')) return obj;
                    do
                    {
                        Space();
                        if (at >= source.Length || source[at] != '"') Fail();
                        string key = String();
                        Need(':');
                        if (obj.ContainsKey(key) || obj.Count >= 4096) Fail();
                        obj.Add(key, Value(depth + 1));
                        if (Eat('}')) return obj;
                        Need(',');
                    } while (true);
                }
                if (c == '[')
                {
                    at++;
                    List<object> list = new List<object>();
                    if (Eat(']')) return list;
                    do
                    {
                        if (list.Count >= 4096) Fail();
                        list.Add(Value(depth + 1));
                        if (Eat(']')) return list;
                        Need(',');
                    } while (true);
                }
                if (c == '"') return String();
                if (c == 't') { Literal("true"); return true; }
                if (c == 'f') { Literal("false"); return false; }
                if (c == 'n') { Literal("null"); return null; }
                return Number();
            }
            private void Literal(string text)
            {
                if (at + text.Length > source.Length ||
                    string.CompareOrdinal(source, at, text, 0, text.Length) != 0) Fail();
                at += text.Length;
            }
            private bool Digit() { return at < source.Length && source[at] >= '0' && source[at] <= '9'; }
            private double Number()
            {
                int start = at;
                if (at < source.Length && source[at] == '-') at++;
                if (!Digit()) Fail();
                if (source[at] == '0') at++;
                else while (Digit()) at++;
                if (at < source.Length && source[at] == '.')
                {
                    at++;
                    if (!Digit()) Fail();
                    while (Digit()) at++;
                }
                if (at < source.Length && (source[at] == 'e' || source[at] == 'E'))
                {
                    at++;
                    if (at < source.Length && (source[at] == '+' || source[at] == '-')) at++;
                    if (!Digit()) Fail();
                    while (Digit()) at++;
                }
                double value;
                if (!double.TryParse(source.Substring(start, at - start), NumberStyles.Float,
                    CultureInfo.InvariantCulture, out value) || double.IsNaN(value) || double.IsInfinity(value)) Fail();
                return value;
            }
            private string String()
            {
                Need('"');
                StringBuilder result = new StringBuilder();
                while (at < source.Length)
                {
                    char c = source[at++];
                    if (c == '"') return result.ToString();
                    if (c < 0x20) Fail();
                    if (c != '\\') { result.Append(c); continue; }
                    if (at >= source.Length) Fail();
                    char escaped = source[at++];
                    switch (escaped)
                    {
                        case '"': result.Append('"'); break;
                        case '\\': result.Append('\\'); break;
                        case '/': result.Append('/'); break;
                        case 'b': result.Append('\b'); break;
                        case 'f': result.Append('\f'); break;
                        case 'n': result.Append('\n'); break;
                        case 'r': result.Append('\r'); break;
                        case 't': result.Append('\t'); break;
                        case 'u':
                            if (at + 4 > source.Length) Fail();
                            int code = 0;
                            for (int i = 0; i < 4; i++)
                            {
                                char h = source[at++];
                                int n = h >= '0' && h <= '9' ? h - '0' :
                                        h >= 'a' && h <= 'f' ? h - 'a' + 10 :
                                        h >= 'A' && h <= 'F' ? h - 'A' + 10 : -1;
                                if (n < 0) Fail();
                                code = (code << 4) | n;
                            }
                            result.Append((char)code);
                            break;
                        default: Fail(); break;
                    }
                }
                Fail();
                return null;
            }
        }
    }
}
