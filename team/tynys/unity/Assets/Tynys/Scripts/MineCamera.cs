using UnityEngine;

namespace Tynys
{
    /// <summary>A compact orthographic camera for the mine diorama.</summary>
    [RequireComponent(typeof(Camera))]
    public sealed class MineCamera : MonoBehaviour
    {
        public Vector3 target = new Vector3(0f, -3f, 0f);
        public float yaw = -22f;
        public float pitch = 40f;
        public float distance = 145f;
        public float orthographicSize = 60f;
        public MineHUD hud;

        private Camera view;
        private Vector3 desiredTarget;
        private bool movingToFocus;
        private Vector3 focusVelocity;
        private float desiredSize = 60f, sizeVelocity;
        private bool dragging;
        private bool panning;
        private Vector3 previousPointer;

        private void Awake()
        {
            view = GetComponent<Camera>();
            view.orthographic = true;
            view.nearClipPlane = 0.3f;
            view.farClipPlane = 600f;
            desiredTarget = target;
        }

        private void Start()
        {
            if (hud == null) hud = FindFirstObjectByType<MineHUD>();
            ApplyCamera();
        }

        private void LateUpdate()
        {
            if (hud == null) hud = FindFirstObjectByType<MineHUD>();
            bool blocked = IsPointerOverUI();
            if (Input.GetKeyDown(KeyCode.Home) && !MineHUD.IsTyping) ResetView();
            if (Input.GetMouseButtonDown(1))
            {
                dragging = !blocked;
                previousPointer = Input.mousePosition;
                movingToFocus = false;
            }
            if (Input.GetMouseButtonDown(2))
            {
                panning = !blocked;
                previousPointer = Input.mousePosition;
                movingToFocus = false;
            }
            Vector3 delta = Input.mousePosition - previousPointer;
            if (dragging && Input.GetMouseButton(1))
            {
                yaw += delta.x * 0.21f;
                pitch = Mathf.Clamp(pitch - delta.y * 0.16f, 25f, 78f);
            }
            if (panning && Input.GetMouseButton(2))
            {
                Vector3 right = Quaternion.Euler(0f, yaw, 0f) * Vector3.right;
                Vector3 forward = Quaternion.Euler(0f, yaw, 0f) * Vector3.forward;
                float unitsPerPixel = orthographicSize * 2f / Mathf.Max(1f, view.pixelHeight);
                target -= right * delta.x * unitsPerPixel;
                target -= forward * delta.y * unitsPerPixel;
                float origin=hud!=null&&hud.command!=null&&!hud.command.SiteView?MineCommandView.Origin.x:0;
                target.x = Mathf.Clamp(target.x, origin-100f, origin+100f);
                target.z = Mathf.Clamp(target.z, -65f, 65f);
                desiredTarget = target;
            }
            if (Input.GetMouseButtonUp(1)) dragging = false;
            if (Input.GetMouseButtonUp(2)) panning = false;
            previousPointer = Input.mousePosition;

            if (!blocked)
            {
                float wheel = Input.mouseScrollDelta.y;
                if (Mathf.Abs(wheel) > 0.001f)
                {
                    movingToFocus = false;
                    orthographicSize = Mathf.Clamp(orthographicSize * Mathf.Pow(0.9f, wheel), 18f, 100f);
                }
            }
            if (movingToFocus)
            {
                target = Vector3.SmoothDamp(target, desiredTarget, ref focusVelocity, .65f, 150f, Time.unscaledDeltaTime);
                orthographicSize = Mathf.SmoothDamp(orthographicSize, desiredSize, ref sizeVelocity, .65f, 90f, Time.unscaledDeltaTime);
                if ((target - desiredTarget).sqrMagnitude < .01f && Mathf.Abs(orthographicSize-desiredSize)<.01f) movingToFocus = false;
            }
            ApplyCamera();
        }

        private void ApplyCamera()
        {
            if (view == null) view = GetComponent<Camera>();
            view.orthographic = true;
            view.orthographicSize = orthographicSize;
            if (hud != null && hud.Visible)
            {
                float scale = Mathf.Min(Screen.width / 1600f, Screen.height / 900f);
                float width = Screen.width / scale;
                float height = Screen.height / scale;
                view.rect = new Rect(290f/width, 126f / height, (width - 634f) / width,
                    (height - 230f) / height);
            }
            else view.rect = new Rect(0f, 0f, 1f, 1f);
            Quaternion rotation = Quaternion.Euler(pitch, yaw, 0f);
            transform.SetPositionAndRotation(target + rotation * new Vector3(0f, 0f, -distance), rotation);
        }

        public bool IsPointerOverUI()
        {
            if (hud == null) hud = FindFirstObjectByType<MineHUD>();
            return hud != null && hud.Visible && hud.ContainsScreenPoint(Input.mousePosition);
        }

        public void ResetView()
        {
            if(hud!=null&&hud.command!=null){hud.command.ShowSite(false);return;}
            yaw = -22f;
            pitch = 40f;
            distance = 145f;
            orthographicSize = 60f;
            desiredTarget = new Vector3(0f, -3f, 0f);
            target = desiredTarget;
            movingToFocus = false;
            ApplyCamera();
        }

        public void SetComposition(Vector3 center,float size)
        {
            target=desiredTarget=center;orthographicSize=desiredSize=size;
            yaw=-32f;pitch=43f;distance=145f;movingToFocus=false;focusVelocity=Vector3.zero;sizeVelocity=0;
            ApplyCamera();
        }

        public void Focus(Vector3 point)
        {
            desiredTarget = new Vector3(point.x, Mathf.Clamp(point.y, -8f, 4f), point.z);
            desiredSize = 32f;
            focusVelocity = Vector3.zero;
            sizeVelocity = 0f;
            movingToFocus = true;
        }
    }
}
