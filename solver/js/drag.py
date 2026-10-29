# -*- coding: utf-8 -*-
"""人类式拖动：反应时间停顿 → 缓入主拖动（含微停顿/抖动）→ 读块位置 → ≤4 次微调 → 驻留后松手。

拖的是可信输入（isTrusted 事件由 iv8 派发），位移与 xPos 的映射来自 config。
"""
from ..config import MAPPING_A, MAPPING_B

# 人类式拖动：先"反应时间"停顿 → 缓入主拖动（含微停顿/抖动）→ 读块位置 → ≤4 次微调 → 收尾驻留后松手
DRAG_JS = r"""
(function(targetX, sEst, sx, sy){
  var h = document.querySelector('#aliyunCaptcha-sliding-slider');
  var pc = document.querySelector('#aliyunCaptcha-puzzle');
  if (!h || !pc) return 'no-slider';
  window.__sd = {trace: [], done: false};
  function mk(t, xx, yy, b){
    return new MouseEvent(t, {bubbles:true, cancelable:true, view:window, clientX:xx, clientY:yy,
      screenX:xx, screenY:yy, button:0, buttons:b, detail:1});
  }
  function fire(t, xx, yy, b){
    var tgt = h;
    try { if (document.elementFromPoint) { var u = document.elementFromPoint(xx, yy); if (u) tgt = u; } } catch(e){}
    tgt.dispatchEvent(mk(t, xx, yy, b));
    document.dispatchEvent(mk(t, xx, yy, b));
    window.dispatchEvent(mk(t, xx, yy, b));
  }
  function pileft(){ var v = parseFloat(pc.style.left); return isNaN(v) ? 0 : v; }
  function slideft(){ var v = parseFloat(h.style.left); return isNaN(v) ? 0 : v; }
  var A = __MAP_A__, B = __MAP_B__;
  var N = 32, i = 0, cur = sx, fixes = 0, pauses = 0;
  fire('mousemove', sx - 26, sy - 9, 0);
  fire('mousedown', sx, sy, 1);
  function approach(){
    var t = i / N;
    // 人类速度曲线：先慢起、中段快、末段减速
    var ease = t < 0.15 ? (t / 0.15) * 0.06
             : 0.06 + (1 - Math.pow(1 - (t - 0.15) / 0.85, 2.6)) * 0.94;
    var x = sx + sEst * ease + (Math.random() * 1.1 - 0.55);
    var y = sy + Math.sin(t * Math.PI) * 1.3 + (Math.random() * 0.9 - 0.45);
    fire('mousemove', x, y, 1);
    cur = x; i++;
    if (i <= N) {
      var dt = 13 + Math.random() * 22;
      if (i === Math.floor(N * 0.45) || i === Math.floor(N * 0.8)) { dt += 70 + Math.random() * 90; pauses++; }
      setTimeout(approach, dt);
    } else {
      setTimeout(check, 150 + Math.random() * 160);
    }
  }
  function check(){
    var p = pileft(), err = targetX - p;
    window.__sd.trace.push(['check' + fixes, Math.round(slideft() * 100) / 100, Math.round(p * 100) / 100,
                            Math.round(err * 100) / 100]);
    if (Math.abs(err) <= 1.5 || fixes >= 4) { settle(); return; }
    var s = slideft();
    var ds = Math.max(-25, Math.min(25, err / Math.max(0.6, 2 * A * s + B)));
    cur += ds;
    fire('mousemove', cur, sy + (Math.random() * 1.2 - 0.6), 1);
    fixes++;
    setTimeout(check, 130 + Math.random() * 110);
  }
  function settle(){
    // 松手前驻留 + 1 次极小抖动（真人收尾常见）
    fire('mousemove', cur + (Math.random() * 0.8 - 0.4), sy + (Math.random() * 0.6 - 0.3), 1);
    setTimeout(function(){
      window.__sd.finalSlide = slideft();
      window.__sd.finalPiece = pileft();
      fire('mouseup', cur, sy, 0);
      window.__sd.done = true;
    }, 120 + Math.random() * 180);
  }
  setTimeout(approach, 130 + Math.random() * 160);   // 反应时间
  return 'drag-started';
})(%s, %s, %s, %s)
""".replace("__MAP_A__", repr(MAPPING_A)).replace("__MAP_B__", repr(MAPPING_B))

