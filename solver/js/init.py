# -*- coding: utf-8 -*-
"""站点同款初始化调用。

默认不传 captchaVerifyCallback：SDK 自己发 VerifyCaptchaV3 拿 securityToken（站点真实路径）。
`with_callback=True` 只用于调试——那样会跳过后端验证，拿不到 securityToken。
"""

INIT_JS = r"""
(function(sceneId, prefix, region, withCallback){
  window.__probe = {events: [], param: null, success: null, fail: null, err: null, verifyResp: null};
  window.AliyunCaptchaConfig = {region: region, prefix: prefix};
  if (typeof window.initAliyunCaptcha !== 'function') return 'no-init';
  var o = {
    SceneId: sceneId, mode: 'popup', element: '#captcha-element', language: 'cn',
    slideStyle: {width: 360, height: 40},
    success: function(t){ window.__probe.success = String(t); window.__probe.events.push('success'); },
    fail: function(e){ window.__probe.fail = String(e); window.__probe.events.push('fail'); },
    onError: function(e){ try{ window.__probe.err = JSON.stringify(e); }catch(x){} window.__probe.events.push('onError'); },
    getInstance: function(i){ window.__inst = i; window.__probe.events.push('getInstance'); }
  };
  // 默认走**站点同款路径**：不提供 captchaVerifyCallback，SDK 自己发 VerifyCaptchaV3 拿 securityToken
  if (withCallback) {
    o.captchaVerifyCallback = function(p, cb){
      window.__probe.param = String(p); window.__probe.events.push('param');
      if (cb) cb({captchaResult: true, bizResult: true});
      return true;
    };
  }
  window.initAliyunCaptcha(o);
  return 'init-called';
})(%s, %s, %s, %s)
"""

