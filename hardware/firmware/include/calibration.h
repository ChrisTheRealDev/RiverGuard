#pragma once
#include <math.h>
#include <stddef.h>
inline float interpolate(float x,float a,float b,float ya,float yb) {
  if(!isfinite(x)||!isfinite(a)||!isfinite(b)||!isfinite(ya)||!isfinite(yb)||fabsf(b-a)<1.0f) return NAN;
  if(x<fminf(a,b)||x>fmaxf(a,b)) return NAN;
  return ya+(x-a)*(yb-ya)/(b-a);
}
inline float calibratedNTU(float mv,const float* volts,const float* ntu,size_t n) {
  if(n<2) return NAN;
  for(size_t i=0;i<n;i++) if(!isfinite(volts[i])||!isfinite(ntu[i])||ntu[i]<0||(i&&volts[i]<=volts[i-1])) return NAN;
  for(size_t i=1;i<n;i++) if(mv>=volts[i-1]&&mv<=volts[i]) return interpolate(mv,volts[i-1],volts[i],ntu[i-1],ntu[i]);
  return NAN;
}
inline float levelAboveDatum(float distance,float reference,float minimum,float maximum) {
  if(!isfinite(distance)||!isfinite(reference)||!isfinite(minimum)||!isfinite(maximum)||minimum<=0||maximum<=minimum||reference<=0) return NAN;
  if(distance<minimum||distance>maximum||distance>reference) return NAN;
  return reference-distance;
}
