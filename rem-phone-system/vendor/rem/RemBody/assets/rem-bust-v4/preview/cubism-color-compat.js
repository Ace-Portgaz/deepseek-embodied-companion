/** Cubism 4.2 per-drawable colors for the pinned pixi-live2d 0.4 renderer.
 * Formula follows Live2D's premultiplied-alpha multiply/screen specification:
 * https://docs.live2d.com/en/cubism-sdk-manual/multiply-color-screen-color-web/
 * Core supplies animated colors; masks retain their original alpha-only shader.
 */
export function installCubismColorCompatibility(PIXI) {
  const prototype=PIXI.live2d.CubismShader_WebGL.prototype;
  if (prototype.remDrawableColors) return;
  const load=prototype.loadShaderProgram,setup=prototype.setupShaderProgram;
  const indices=new WeakMap(),locations=new WeakMap();
  const sample=/texture2D\(s_texture0\s*,\s*v_texCoord\)/g;
  prototype.loadShaderProgram=function(vertex,fragment) {
    if (fragment.includes('col_formask') || fragment.includes('gl_FragColor = texture2D')) {
      fragment=fragment.replace(sample,'remSample()').replace('void main()',
        'uniform vec4 u_remMultiply;uniform vec4 u_remScreen;'+
        'vec4 remSample(){vec4 c=texture2D(s_texture0,v_texCoord);'+
        'c.rgb*=u_remMultiply.rgb;'+
        'c.rgb=c.rgb+u_remScreen.rgb*c.a-c.rgb*u_remScreen.rgb;return c;}void main()');
    }
    return load.call(this,vertex,fragment);
  };
  prototype.setupShaderProgram=function(...args) {
    setup.apply(this,args);
    const renderer=args[0];
    if (renderer.getClippingContextBufferForMask()) return;
    const raw=renderer.getModel().getModel();
    let lookup=indices.get(raw);
    if (!lookup) {
      lookup=new WeakMap();
      raw.drawables.vertexPositions.forEach((positions,index)=>lookup.set(positions,index));
      indices.set(raw,lookup);
    }
    const names=PIXI.live2d.ShaderNames,blend=PIXI.live2d.CubismBlendMode;
    const offset=renderer.getClippingContextBufferForDraw()?(args[12]?2:1):0;
    const kind=args[8]===blend.CubismBlendMode_Additive?names.ShaderNames_AddPremultipliedAlpha:
      args[8]===blend.CubismBlendMode_Multiplicative?names.ShaderNames_MultPremultipliedAlpha:names.ShaderNames_NormalPremultipliedAlpha;
    const index=lookup.get(args[3]),gl=this.gl,program=this._shaderSets[kind+offset].shaderProgram;
    let uniforms=locations.get(program);
    if (!uniforms) {
      uniforms={multiply:gl.getUniformLocation(program,'u_remMultiply'),screen:gl.getUniformLocation(program,'u_remScreen')};
      locations.set(program,uniforms);
    }
    const m=raw.drawables.multiplyColors,s=raw.drawables.screenColors,i=index*4;
    if (index!==undefined && m && s) {
      gl.uniform4f(uniforms.multiply,m[i],m[i+1],m[i+2],m[i+3]);
      gl.uniform4f(uniforms.screen,s[i],s[i+1],s[i+2],s[i+3]);
    } else {
      gl.uniform4f(uniforms.multiply,1,1,1,1);gl.uniform4f(uniforms.screen,0,0,0,1);
    }
  };
  prototype.remDrawableColors=true;
}
