Shader "Tynys/EnergyFlow"
{
    Properties
    {
        _MainTex ("Pulse texture", 2D) = "white" {}
        [HDR] _Color ("Energy color", Color) = (0.3,1.6,1.2,1)
        _FlowOffset ("Flow phase", Float) = 0
        _Strength ("Active power", Float) = 1
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" }
        Blend SrcAlpha OneMinusSrcAlpha
        ZWrite Off Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #include "UnityCG.cginc"
            sampler2D _MainTex; float4 _Color; float _FlowOffset, _Strength;
            struct appdata { float4 vertex:POSITION; float2 uv:TEXCOORD0; };
            struct v2f { float4 vertex:SV_POSITION; float2 uv:TEXCOORD0; UNITY_FOG_COORDS(1) };
            v2f vert(appdata v) { v2f o; o.vertex=UnityObjectToClipPos(v.vertex); o.uv=float2(v.uv.x*.18+_FlowOffset,v.uv.y); UNITY_TRANSFER_FOG(o,o.vertex); return o; }
            half4 frag(v2f i):SV_Target
            {
                half4 c=tex2D(_MainTex,i.uv)*_Color;
                c.rgb *= _Strength; c.a *= lerp(.3,1,_Strength);
                UNITY_APPLY_FOG(i.fogCoord,c); return c;
            }
            ENDCG
        }
    }
}
