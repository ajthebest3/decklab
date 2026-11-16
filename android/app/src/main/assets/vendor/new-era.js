// DeckLab New Era. Original procedural artwork; no external assets or requests.
export function initNewEra(){
 const root=document.querySelector('.era-hero');if(!root)return;
 const canvas=root.querySelector('canvas'),wrap=root.querySelector('.era-scene'),status=root.querySelector('#render-status'),motion=root.querySelector('#motion');
 const reduced=matchMedia('(prefers-reduced-motion: reduce)'),mobile=matchMedia('(max-width: 640px)').matches;
 let gl,program,buffer,raf=0,inView=false,wants=false,lost=false,shape=0,target=0,manualShape=0,angleX=0,angleY=0,frames=0,time=0,last=0,dragging=false,lastX=0,lastY=0;
 const state={ready:false,frames:0,motion:false,view:'solid',contextLost:false};window.__decklabScene=state;
 function fallback(){root.classList.remove('era-ready');state.ready=false;state.motion=false;cancelAnimationFrame(raf);raf=0;status.textContent='STATIC PARTICLE STUDY';root.querySelectorAll('.era-tools button').forEach(b=>b.disabled=true);}
 try{gl=canvas.getContext('webgl',{alpha:true,antialias:false,powerPreference:'low-power',preserveDrawingBuffer:true});if(!gl)throw Error('WebGL unavailable');}catch(e){fallback();return state;}
 const vertex=`precision highp float;
attribute vec4 seed;
uniform float clock,shape,aspect,pixelRatio,turnX,turnY;
varying vec3 tint;
varying float opacity;
const float PI=3.14159265359;
const float TAU=6.28318530718;
void main(){
 float t=seed.x;float s=seed.y;float r=seed.z;float q=seed.w;
 float h1=fract(sin(q*127.1+s*311.7)*43758.5453);
 float h2=fract(sin(q*269.5+s*183.3)*43758.5453);
 float warp=t+0.03*sin(t*TAU*3.0+s*TAU)+0.006*sin(t*TAU*7.0+s*TAU*2.0);
 float ang=warp*TAU+clock*(0.028+0.03*s);
 float braidA=sin(ang*4.0+s*TAU);
 float braidB=cos(ang*3.0-s*TAU+1.3);
 float band=fract(s*7.37)-0.5;
 float radius=0.735+band*0.062+0.02*sin(ang*2.0+clock*0.11)+0.007*braidB;
 vec2 dir=vec2(cos(ang),sin(ang));
 vec2 nrm=vec2(-dir.y,dir.x);
 float weave=(braidA*0.6+braidB*0.4)*0.032*(0.55+0.45*r);
 vec2 hp=dir*radius+nrm*weave+vec2(h1-0.5,h2-0.5)*0.008*smoothstep(0.35,1.0,r);
 vec3 halo=vec3(hp,braidA*0.06+0.022*sin(ang*5.0+s*TAU+clock*0.2)+(h2-0.5)*0.05);
 float phi=acos(clamp(2.0*t-1.0,-1.0,1.0));
 float theta=s*TAU+clock*0.05;
 float rr=0.5+0.045*sin(theta*5.0+phi*7.0+clock*0.3)+0.02*(h1-0.5);
 vec3 orbit=vec3(sin(phi)*cos(theta),cos(phi),sin(phi)*sin(theta))*rr+vec3(h1-0.5,(h2-0.5)*0.6,h2-0.5)*0.022;
 float gr=sqrt(t)*0.94;
 float arm=floor(s*5.0);
 float sp=gr*6.4+arm*(TAU/5.0)+(fract(s*5.0)-0.5)*0.55+clock*0.03;
 vec3 galaxy=vec3(cos(sp)*gr,sin(sp)*gr*0.44,(h2-0.5)*0.14*(1.0-gr*0.6));
 float k1=smoothstep(0.0,1.0,clamp(shape,0.0,1.0));
 float k2=smoothstep(0.0,1.0,clamp(shape-1.0,0.0,1.0));
 vec3 p=mix(mix(halo,orbit,k1),galaxy,k2);
 float cx=cos(turnX),sx=sin(turnX),cy=cos(turnY),sy=sin(turnY);
 p=vec3(p.x,p.y*cx-p.z*sx,p.y*sx+p.z*cx);
 p=vec3(p.x*cy+p.z*sy,p.y,-p.x*sy+p.z*cy);
 p.xy*=1.0/(1.0+p.z*0.25);
 gl_Position=vec4(p.x/aspect,p.y,0.0,1.0);
 float depth=clamp(0.5+p.z*1.4,0.0,1.0);
 float spark=step(0.965,fract(sin(q*91.7+s*57.3)*43758.5453));
 gl_PointSize=clamp((1.4+q*2.4+spark*2.1)*pixelRatio*(0.72+depth*0.68),1.0*pixelRatio,7.5*pixelRatio);
 float w=clamp(p.y*0.85+0.52,0.0,1.0);
 vec3 blue=mix(vec3(0.16,0.32,0.98),vec3(0.42,0.64,1.0),q);
 vec3 lilac=vec3(0.74,0.63,0.99);
 vec3 peach=mix(vec3(0.99,0.6,0.42),vec3(1.0,0.84,0.71),q);
 vec3 col=mix(blue,lilac,smoothstep(0.1,0.56,w));
 col=mix(col,peach,smoothstep(0.56,0.94,w));
 col*=0.88+0.24*h1;
 tint=col;
 float pulse=pow(0.5+0.5*sin(ang*2.0-clock*0.9+s*TAU*0.12),6.0);
 opacity=clamp((0.09+0.26*q)*(0.45+depth*0.75)*(0.72+pulse*0.85)*(1.0+spark*0.9),0.0,0.95);
}`;
 const fragment=`precision mediump float;
varying vec3 tint;
varying float opacity;
void main(){
 vec2 uv=gl_PointCoord-0.5;
 float d=length(uv)*2.0;
 if(d>1.0)discard;
 float core=exp(-d*d*15.0);
 float glow=exp(-d*d*3.0);
 float edge=1.0-smoothstep(0.8,1.0,d);
 float alpha=(glow*0.42+core*0.80)*opacity*edge*1.85;
 gl_FragColor=vec4(tint*(0.88+core*0.55),alpha);
}`;
 function shader(type,source){const sh=gl.createShader(type);gl.shaderSource(sh,source);gl.compileShader(sh);if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))throw Error('Shader unavailable');return sh;}
 try{program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vertex));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragment));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('Program unavailable');}catch(e){fallback();return state;}
 gl.useProgram(program);const count=mobile?16000:36000,data=new Float32Array(count*4);
 // Ordered strands provide the finely woven texture of the halo.
 let rng=5831;function random(){rng=(rng*1664525+1013904223)>>>0;return rng/4294967296;}
 for(let i=0;i<count;i++){const strand=i%72,step=Math.floor(i/72);data[i*4]=step/Math.ceil(count/72);data[i*4+1]=strand/72;data[i*4+2]=random();data[i*4+3]=random();}
 buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);const seed=gl.getAttribLocation(program,'seed');gl.enableVertexAttribArray(seed);gl.vertexAttribPointer(seed,4,gl.FLOAT,false,0,0);
 const uniforms={};for(const key of ['clock','shape','aspect','pixelRatio','turnX','turnY'])uniforms[key]=gl.getUniformLocation(program,key);
 gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);gl.clearColor(0,0,0,0);
 function render(){if(lost||document.hidden||!inView)return;gl.clear(gl.COLOR_BUFFER_BIT);for(const [key,value] of Object.entries({clock:time,shape,aspect:canvas.width/canvas.height,pixelRatio:Math.min(devicePixelRatio,1.7),turnX:angleX,turnY:angleY}))gl.uniform1f(uniforms[key],value);gl.drawArrays(gl.POINTS,0,count);state.frames=++frames;state.shape=shape;state.target=target;}
 function tick(now){raf=0;if(lost||document.hidden||!inView)return;const delta=Math.min((now-(last||now))/1000,.05);last=now;const moving=wants&&!reduced.matches;if(moving)time+=delta;shape+=Math.sign(target-shape)*Math.min(Math.abs(target-shape),delta*1.5);render();if(moving||Math.abs(shape-target)>.001)raf=requestAnimationFrame(tick);state.motion=moving;}
 function update(){cancelAnimationFrame(raf);raf=0;last=0;state.motion=wants&&!reduced.matches&&inView&&!document.hidden&&!lost;motion.disabled=reduced.matches||lost;motion.textContent=reduced.matches?'Reduced motion':wants?'Motion on':'Motion off';motion.setAttribute('aria-pressed',String(wants&&!reduced.matches));if(!lost&&inView&&!document.hidden){if(state.motion||Math.abs(shape-target)>.001)raf=requestAnimationFrame(tick);else render();}}
 function resize(){const r=wrap.getBoundingClientRect();if(!r.width||!r.height)return;const dpr=Math.min(devicePixelRatio,1.7);canvas.width=Math.round(r.width*dpr);canvas.height=Math.round(r.height*dpr);gl.viewport(0,0,canvas.width,canvas.height);render();}
 function setShape(value){manualShape=value;target=value;state.view=['solid','wire','explode'][value];root.querySelectorAll('[data-era-shape]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.eraShape)===value)));root.querySelector('.era-scene-label').textContent=['01 — THE SIGNAL','02 — THE CONNECTION','03 — THE BIGGER PICTURE'][value];if(reduced.matches)shape=target;update();}
 root.querySelectorAll('[data-era-shape]').forEach(b=>b.onclick=()=>setShape(Number(b.dataset.eraShape)));
 motion.onclick=()=>{wants=!wants;update();};root.querySelector('#reset-scene').onclick=()=>{angleX=angleY=0;setShape(0);};
 canvas.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();angleX+=e.key==='ArrowUp'?-.1:e.key==='ArrowDown'?.1:0;angleY+=e.key==='ArrowLeft'?-.1:e.key==='ArrowRight'?.1:0;render();});
 canvas.addEventListener('pointerdown',e=>{if(e.pointerType==='touch'||e.button!==0)return;dragging=true;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture(e.pointerId);});
 canvas.addEventListener('pointermove',e=>{if(!dragging)return;angleY+=(e.clientX-lastX)*.004;angleX+=(e.clientY-lastY)*.004;lastX=e.clientX;lastY=e.clientY;render();});
 for(const name of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(name,()=>dragging=false);
 // Scroll gently opens the halo into a galaxy, independently of market refresh.
 let scrollRaf=0;addEventListener('scroll',()=>{if(scrollRaf||reduced.matches||!inView)return;scrollRaf=requestAnimationFrame(()=>{scrollRaf=0;const rect=root.getBoundingClientRect();if(rect.bottom>0){target=rect.top<0?Math.max(manualShape,Math.min(2,-rect.top/root.clientHeight*2.7)):manualShape;update();}});},{passive:true});
 new ResizeObserver(resize).observe(wrap);new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;update();},{threshold:.01}).observe(root);
 let lastPreference=reduced.matches;
 function syncPreference(){if(document.hidden||lastPreference===reduced.matches)return;lastPreference=reduced.matches;if(lastPreference){wants=false;shape=target;}update();}
 document.addEventListener('visibilitychange',()=>{syncPreference();update();});reduced.addEventListener('change',syncPreference);
 // Some embedded/headless engines update MediaQueryList.matches without dispatching change.
 // This check never renders unless the preference changed, and skips hidden documents.
 setInterval(syncPreference,1000);
 canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();lost=true;state.contextLost=true;fallback();});
 window.captureScene=()=>{render();return canvas.toDataURL('image/png');};
 // Actual runtime route visibility; the design preview has its own page router.
 if(document.querySelector('#view')){const syncRoute=()=>{root.hidden=!!location.hash&&location.hash!=='#overview';};addEventListener('hashchange',syncRoute);syncRoute();}
 state.ready=true;state.particles=count;root.classList.add('era-ready');status.textContent='PARTICLE STUDY / DRAG TO EXPLORE';resize();return state;
}
