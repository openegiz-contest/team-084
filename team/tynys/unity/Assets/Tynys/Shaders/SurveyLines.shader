Shader "Tynys/SurveyLines"
{
    Properties { _Color("Colour", Color)=(0.2,0.8,1,0.7) }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" }
        Pass
        {
            Blend SrcAlpha One
            ZWrite Off
            Offset -1,-1
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            fixed4 _Color;
            struct Input { float4 vertex:POSITION; };
            struct Output { float4 vertex:SV_POSITION; };
            Output vert(Input v)
            {
                Output o;o.vertex=UnityObjectToClipPos(v.vertex);
                // Lines share the solid geometry. Pull only their depth forward to prevent surface flicker.
                #if defined(UNITY_REVERSED_Z)
                o.vertex.z+=0.00015*o.vertex.w;
                #else
                o.vertex.z-=0.00015*o.vertex.w;
                #endif
                return o;
            }
            fixed4 frag(Output i):SV_Target { return _Color; }
            ENDCG
        }
    }
}
