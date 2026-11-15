export const BODY_LABELS={head:'头顶和头发',face:'脸颊',hand:'手和手臂',body:'上身和衣服',legs:'腿和脚',tail:'尾巴'};
export function triangleContains(x,y,p,a,b,c){
 const ax=p[a*2],ay=p[a*2+1],bx=p[b*2],by=p[b*2+1],cx=p[c*2],cy=p[c*2+1];
 const area=(bx-ax)*(cy-ay)-(by-ay)*(cx-ax);if(Math.abs(area)<1e-10)return false;
 const u=((bx-x)*(cy-y)-(by-y)*(cx-x))/area;
 const v=((cx-x)*(ay-y)-(cy-y)*(ax-x))/area;
 return u>=-1e-6&&v>=-1e-6&&u+v<=1+1e-6;
}
export function hitMeshes(x,y,drawables,regions,opaque=()=>true){
 // Check current deformed mesh triangles in front-to-back order, not screen rectangles.
 const order=Array.from(drawables.ids,(_,i)=>i).sort((a,b)=>drawables.renderOrders[b]-drawables.renderOrders[a]);
 for(const i of order){
  const region=regions[drawables.ids[i]];if(!BODY_LABELS[region]||drawables.opacities[i]<.15)continue;
  const p=drawables.vertexPositions[i],tri=drawables.indices[i];
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  for(let j=0;j<p.length;j+=2){minX=Math.min(minX,p[j]);maxX=Math.max(maxX,p[j]);minY=Math.min(minY,p[j+1]);maxY=Math.max(maxY,p[j+1]);}
  if(x<minX||x>maxX||y<minY||y>maxY)continue;
  for(let j=0;j<tri.length;j+=3)if(triangleContains(x,y,p,tri[j],tri[j+1],tri[j+2])&&opaque(i,tri[j],tri[j+1],tri[j+2],x,y))return region;
 }
 return null;
}
