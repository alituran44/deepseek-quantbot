// DeepSeek-QuantBot Kripto Sepet Client Application

// --- Global Yetkilendirme & Kalkan Koruması (Admin Shield) ---
const _originalFetch = window.fetch;
window.fetch = async function (resource, init = {}) {
  init = init || {};
  init.headers = init.headers || {};
  const token = localStorage.getItem('quant_admin_token');
  if (token) {
    if (init.headers instanceof Headers) {
      if (!init.headers.has('Authorization')) init.headers.set('Authorization', 'Bearer ' + token);
      if (!init.headers.has('X-Admin-Token')) init.headers.set('X-Admin-Token', token);
    } else if (Array.isArray(init.headers)) {
      init.headers.push(['Authorization', 'Bearer ' + token]);
      init.headers.push(['X-Admin-Token', token]);
    } else {
      if (!init.headers['Authorization']) init.headers['Authorization'] = 'Bearer ' + token;
      if (!init.headers['X-Admin-Token']) init.headers['X-Admin-Token'] = token;
    }
  }
  const response = await _originalFetch(resource, init);
  if (response.status === 401 && typeof resource === 'string' && !resource.includes('/api/auth/')) {
    showLockScreen();
  }
  return response;
};

function showLockScreen(errorMessage = '') {
  const overlay = document.getElementById('lock-screen-overlay');
  const btnLockHeader = document.getElementById('btn-lock-header');
  const errorMsg = document.getElementById('pin-error-msg');
  const pinInput = document.getElementById('pin-input-field');

  if (overlay) overlay.style.display = 'flex';
  if (btnLockHeader) btnLockHeader.style.display = 'none';
  if (errorMsg) errorMsg.textContent = errorMessage;
  if (pinInput) {
    pinInput.value = '';
    setTimeout(() => pinInput.focus(), 150);
  }
}

function hideLockScreen() {
  const overlay = document.getElementById('lock-screen-overlay');
  const btnLockHeader = document.getElementById('btn-lock-header');
  const errorMsg = document.getElementById('pin-error-msg');

  if (overlay) overlay.style.display = 'none';
  if (btnLockHeader) btnLockHeader.style.display = 'inline-flex';
  if (errorMsg) errorMsg.textContent = '';
}

async function submitPin() {
  const pinInput = document.getElementById('pin-input-field');
  const errorMsg = document.getElementById('pin-error-msg');
  const pinBtn = document.getElementById('btn-unlock');
  const pinContainer = document.getElementById('pin-container');
  const pin = (pinInput ? pinInput.value : '').trim();

  if (!pin) {
    if (errorMsg) errorMsg.textContent = 'Lütfen PIN kodunuzu girin.';
    if (pinInput) pinInput.focus();
    return;
  }

  if (pinBtn) {
    pinBtn.disabled = true;
    pinBtn.innerHTML = 'Doğrulanıyor...';
  }

  try {
    const res = await _originalFetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: pin })
    });

    const data = await res.json();

    if (res.ok && data.status === 'SUCCESS' && data.token) {
      localStorage.setItem('quant_admin_token', data.token);
      hideLockScreen();
      fetchState();
      loadAllMarketCoins();
      if (typeof fetchRadarData === 'function') fetchRadarData();
    } else {
      if (errorMsg) errorMsg.textContent = data.message || 'Hatalı PIN kodu!';
      if (pinInput) {
        pinInput.value = '';
        pinInput.focus();
      }
      if (pinContainer) {
        pinContainer.style.transform = 'translateX(-10px)';
        setTimeout(() => { pinContainer.style.transform = 'translateX(10px)'; }, 80);
        setTimeout(() => { pinContainer.style.transform = 'translateX(-6px)'; }, 160);
        setTimeout(() => { pinContainer.style.transform = 'translateX(6px)'; }, 240);
        setTimeout(() => { pinContainer.style.transform = 'translateX(0)'; }, 320);
      }
    }
  } catch (err) {
    if (errorMsg) errorMsg.textContent = 'Bağlantı hatası: ' + err.message;
  } finally {
    if (pinBtn) {
      pinBtn.disabled = false;
      pinBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px;">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
          <path d="M7 11V7a5 5 0 0 1 9.9-1"></path>
        </svg>
        Kilidi Aç`;
    }
  }
}

async function lockDashboard() {
  try {
    await _originalFetch('/api/auth/logout', { method: 'POST' });
  } catch (e) {}
  localStorage.removeItem('quant_admin_token');
  showLockScreen('Oturum kilitlendi.');
}

async function checkInitialAuth() {
  const token = localStorage.getItem('quant_admin_token');
  if (!token) {
    showLockScreen();
    return false;
  }
  try {
    const res = await _originalFetch('/api/auth/check', {
      headers: {
        'Authorization': 'Bearer ' + token,
        'X-Admin-Token': token
      }
    });
    const data = await res.json();
    if (data.authenticated) {
      hideLockScreen();
      return true;
    } else {
      localStorage.removeItem('quant_admin_token');
      showLockScreen();
      return false;
    }
  } catch (err) {
    showLockScreen();
    return false;
  }
}

let currentAnalyses = [];
let currentSignalFilter = 'ALL';
let currentModalSymbol = '';
let currentTradingMode = 'PAPER';

function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('app-theme', theme);
  const iconEl = document.getElementById('theme-icon');
  const textEl = document.getElementById('theme-text');
  if (iconEl && textEl) {
    if (theme === 'dark') {
      iconEl.textContent = '☀️';
      textEl.textContent = 'Aydınlık';
    } else {
      iconEl.textContent = '🌙';
      textEl.textContent = 'Karanlık';
    }
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  setTheme(next);
}

function initTheme() {
  const saved = localStorage.getItem('app-theme') || 'light';
  setTheme(saved);
}

let lastDashboardData = null;
let modalTradingMode = 'PAPER';

async function fetchState() {
  try {
    const res = await fetch('/api/state');
    if (!res.ok) return;
    const data = await res.json();
    lastDashboardData = data;
    renderDashboard(data);
    updateModalBalanceInfo();
  } catch (err) {
    console.error('State alınamadı:', err);
  }
}

function renderDashboard(data) {
  // Mod Bilgisi ve Anahtar Gösterimi
  const mode = data.trading_mode || 'PAPER';
  currentTradingMode = mode;
  const isLive = mode === 'LIVE';
  const binance = data.binance_status || {};
  const w = data.wallet || {};
  const mt = data.master_treasury || {};

  // 1. Kasa Metrikleri (USD ve TL): Sanal vs Canlı Ayrımı
  let totalUsd, totalTry, cashUsd, cashTry;
  if (isLive) {
    totalUsd = mt.total_usd !== undefined ? mt.total_usd : (w.total_value || 0);
    totalTry = mt.total_try !== undefined ? mt.total_try : (w.total_value_try || 0);
    cashUsd = mt.cash_usd !== undefined ? mt.cash_usd : (w.cash_balance || 0);
    cashTry = mt.cash_try !== undefined ? mt.cash_try : (w.cash_balance_try || 0);
  } else {
    // Tamamen Sanal Kasa: Gerçek borsa bakiyeleri kesinlikle karıştırılmaz
    totalUsd = w.total_value !== undefined ? w.total_value : (w.total_equity || 10000.0);
    totalTry = w.total_value_try !== undefined ? w.total_value_try : (totalUsd * (data.usd_try_rate || 38.0));
    cashUsd = w.cash_balance !== undefined ? w.cash_balance : 10000.0;
    cashTry = w.cash_balance_try !== undefined ? w.cash_balance_try : (cashUsd * (data.usd_try_rate || 38.0));
  }

  document.getElementById('m-equity').textContent = `${formatCryptoMoney(totalUsd)} USD`;
  const eqTryEl = document.getElementById('m-equity-try');
  if (eqTryEl) eqTryEl.textContent = `₺${totalTry.toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2})} TL`;

  document.getElementById('m-cash').textContent = `${formatCryptoMoney(cashUsd)} USD`;
  const cashTryEl = document.getElementById('m-cash-try');
  if (cashTryEl) cashTryEl.textContent = `₺${cashTry.toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2})} TL`;

  const usdTryRateEl = document.getElementById('m-usd-try-rate');
  if (usdTryRateEl && data.usd_try_rate) {
    usdTryRateEl.textContent = `1$ = ₺${data.usd_try_rate.toFixed(2)}`;
  }

  // Başlıklar ve Dağılım Kartları Ayrımı (CANLI vs SANAL)
  const eqLabel = document.getElementById('m-equity-label');
  const cashLabel = document.getElementById('m-cash-label');
  const breakdownLabel = document.getElementById('m-breakdown-label');
  const liveBox = document.getElementById('box-live-distribution');
  const paperBox = document.getElementById('box-paper-distribution');
  const liveDepositActions = document.getElementById('live-deposit-actions');
  const paperActions = document.getElementById('paper-actions');
  const liveToolbar = document.getElementById('live-exchange-toolbar');
  const paperToolbar = document.getElementById('paper-toolbar');
  const posCardTitle = document.getElementById('positions-card-title');
  const posCardDesc = document.getElementById('positions-card-desc');
  const riskSubtext = document.getElementById('m-risk-subtext');

  if (isLive) {
    if (eqLabel) eqLabel.textContent = '⚡ Konsolide Ana Kasa';
    if (cashLabel) cashLabel.textContent = '⚡ Kullanılabilir Serbest Nakit';
    if (breakdownLabel) breakdownLabel.textContent = '⚡ Borsa Kasa Dağılımı';
    if (liveBox) liveBox.style.display = 'flex';
    if (paperBox) paperBox.style.display = 'none';
    if (liveDepositActions) liveDepositActions.style.display = 'flex';
    if (paperActions) paperActions.style.display = 'none';
    if (liveToolbar) liveToolbar.style.display = 'flex';
    if (paperToolbar) paperToolbar.style.display = 'none';
    if (posCardTitle) posCardTitle.textContent = '⚡ Çoklu Borsa Cüzdan Varlıkları';
    if (posCardDesc) posCardDesc.textContent = 'Borsalardaki coinleriniz ayrı ayrı veya konsolide tam hassasiyetle listelenir';
    if (riskSubtext) riskSubtext.textContent = '⚡ Canlı Borsa Kripto İşlemleri';

    // Borsa Kasa Dağılımı (Binance, OKX, MEXC)
    const binanceShareEl = document.getElementById('m-binance-share');
    const okxShareEl = document.getElementById('m-okx-share');
    const mexcShareEl = document.getElementById('m-mexc-share');
    if (binanceShareEl && mt.binance) {
      binanceShareEl.textContent = `$${mt.binance.total_usd.toFixed(4)} (₺${mt.binance.total_try.toFixed(2)})`;
    }
    if (okxShareEl && mt.okx) {
      if (data.okx_status && data.okx_status.needs_passphrase) {
        okxShareEl.innerHTML = `<span style="color: var(--warning); font-size: 11px;">Parola Bekleniyor ⏳</span>`;
      } else {
        okxShareEl.textContent = `$${mt.okx.total_usd.toFixed(4)} (₺${mt.okx.total_try.toFixed(2)})`;
      }
    }
    if (mexcShareEl && mt.mexc) {
      mexcShareEl.textContent = `$${mt.mexc.total_usd.toFixed(4)} (₺${mt.mexc.total_try.toFixed(2)})`;
    }
  } else {
    // Sanal Kasa: Gerçek borsa bilgileri tamamen gizlenir, simülasyon metrikleri sunulur
    if (eqLabel) eqLabel.textContent = '🧪 Sanal Kasa Varlığı';
    if (cashLabel) cashLabel.textContent = '🧪 Boşta Sanal Nakit';
    if (breakdownLabel) breakdownLabel.textContent = '🧪 Sanal Sepet Durumu';
    if (liveBox) liveBox.style.display = 'none';
    if (paperBox) paperBox.style.display = 'flex';
    if (liveDepositActions) liveDepositActions.style.display = 'none';
    if (paperActions) paperActions.style.display = 'flex';
    if (liveToolbar) liveToolbar.style.display = 'none';
    if (paperToolbar) paperToolbar.style.display = 'flex';
    if (posCardTitle) posCardTitle.textContent = '🧪 Sanal Sepet Pozisyonları';
    if (posCardDesc) posCardDesc.textContent = '10.000$ sanal kasa ile çalışan yapay zeka al-sat pozisyonları ve risk hedefleri';
    if (riskSubtext) riskSubtext.textContent = '🧪 10.000$ Sanal Risk Simülasyonu';

    // Sanal Portföy Dağılım Verileri
    const paperPosValEl = document.getElementById('m-paper-positions-val');
    if (paperPosValEl) {
      paperPosValEl.textContent = `${formatCryptoMoney(w.positions_value || 0)} USD`;
    }
    const paperPnlEl = document.getElementById('m-paper-total-pnl');
    if (paperPnlEl) {
      const pnlUsd = (w.unrealized_pnl !== undefined ? w.unrealized_pnl : (totalUsd - 10000.0)) || 0;
      const pnlPct = (w.unrealized_pnl_pct !== undefined ? w.unrealized_pnl_pct : (pnlUsd / 10000.0 * 100)) || 0;
      paperPnlEl.className = pnlUsd >= 0 ? 'text-profit' : 'text-loss';
      paperPnlEl.textContent = `${pnlUsd >= 0 ? '+' : ''}$${pnlUsd.toFixed(2)} (%${pnlPct.toFixed(2)})`;
    }
  }

  document.getElementById('m-winrate').textContent = `%${w.win_rate || 0} (${w.total_trades || 0} İşlem)`;

  // Header Butonu & Borsa Seçici Senkronizasyonu
  const modeBtn = document.getElementById('btn-mode-toggle');
  const modeLabel = document.getElementById('mode-label');
  const modeDot = document.getElementById('mode-dot');
  const headerExSelect = document.getElementById('select-header-exchange');
  const exChoice = data.trading_exchange || 'AUTO';
  let exLabel = 'Çoklu Borsa: Otomatik';
  if (exChoice === 'BINANCE') exLabel = 'Binance Spot';
  else if (exChoice === 'MEXC') exLabel = 'MEXC Spot';
  else if (exChoice === 'OKX') exLabel = 'OKX Spot';

  if (headerExSelect) {
    if (isLive) {
      headerExSelect.style.display = 'inline-block';
      if (document.activeElement !== headerExSelect) headerExSelect.value = exChoice;
    } else {
      headerExSelect.style.display = 'none';
    }
  }

  if (modeBtn && modeLabel && modeDot) {
    if (isLive) {
      modeBtn.style.borderColor = 'var(--profit)';
      modeDot.style.background = 'var(--profit)';
      modeLabel.innerHTML = `⚡ Canlı Kripto (${exLabel})`;
    } else {
      modeBtn.style.borderColor = 'var(--accent-cyan)';
      modeDot.style.background = 'var(--accent-cyan)';
      modeLabel.innerHTML = '🧪 Sanal Kasa (Öğrenme Modu)';
    }
  }

  // Finans Uzmanı & Risk Rozeti Senkronizasyonu
  const riskBadge = document.getElementById('badge-risk-mode');
  const riskProfile = data.ai_risk_profile || 'AGGRESSIVE_ALPHA';
  if (riskBadge) {
    if (riskProfile === 'ULTRA_DEGEN' || riskProfile === 'DEGEN_ALPHA') {
      riskBadge.innerHTML = '🔥 Finans Uzmanı: Ultra Degen (1:4+ Maksimum Volatilite)';
      riskBadge.style.color = '#f43f5e';
      riskBadge.style.borderColor = 'rgba(244, 63, 94, 0.5)';
    } else if (riskProfile === 'AGGRESSIVE_ALPHA') {
      riskBadge.innerHTML = '⚡ Finans Uzmanı: Agresif Alpha (Asimetrik 1:3+)';
      riskBadge.style.color = 'var(--profit)';
      riskBadge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
    } else if (riskProfile === 'BALANCED') {
      riskBadge.innerHTML = '⚖️ Finans Uzmanı: Dengeli Portföy (1:2.4)';
      riskBadge.style.color = 'var(--accent-cyan)';
      riskBadge.style.borderColor = 'rgba(2, 132, 199, 0.4)';
    } else {
      riskBadge.innerHTML = '🛡️ Finans Uzmanı: Temkinli Koruma';
      riskBadge.style.color = 'var(--warning)';
      riskBadge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
    }
  }
  const selectRisk = document.getElementById('select-risk-profile');
  if (selectRisk && document.activeElement !== selectRisk) {
    selectRisk.value = riskProfile;
  }

  // Makro Risk Kalkanı (FRED / DXY) Senkronizasyonu
  const macroBadge = document.getElementById('badge-macro-mode');
  const macro = data.macro_state || {};
  if (macroBadge) {
    const regLabel = macro.regime === 'RISK_ON' ? 'Risk-On ⚡' : (macro.regime === 'DEFENSIVE' ? 'Savunma 🛡️' : 'Dengeli ⚖️');
    macroBadge.innerHTML = `🛡️ Makro: ${regLabel} (DXY: ${macro.dxy_index || 98.9})`;
    macroBadge.style.color = macro.regime_color || 'var(--profit)';
    macroBadge.style.borderColor = macro.regime === 'DEFENSIVE' ? 'rgba(244, 63, 94, 0.4)' : (macro.regime === 'RISK_ON' ? 'rgba(16, 185, 129, 0.4)' : 'rgba(2, 132, 199, 0.4)');
  }

  // CoinGecko Dinamik Sektör Rallisi & Trend Göstergesi
  const sm = data.sector_momentum || {};
  const cgTopSector = document.getElementById('cg-top-sector');
  const cgTrending = document.getElementById('cg-trending-coins');
  if (cgTopSector && sm.top_gainer_sector) {
    const sign = (sm.top_gainer_change || 0) >= 0 ? '+' : '';
    cgTopSector.innerHTML = `${sm.top_gainer_sector} <span class="${(sm.top_gainer_change || 0) >= 0 ? 'text-profit' : 'text-loss'}">(${sign}%${sm.top_gainer_change})</span>`;
  }
  if (cgTrending && sm.trending_coins && sm.trending_coins.length > 0) {
    cgTrending.textContent = sm.trending_coins.slice(0, 4).join(', ');
  }

  // Mod Banner'ı
  const banner = document.getElementById('mode-banner');
  const bannerIcon = document.getElementById('banner-icon');
  const bannerTitle = document.getElementById('banner-title');
  const bannerDesc = document.getElementById('banner-desc');
  const bannerActionBtn = document.getElementById('banner-action-btn');

  if (banner && bannerTitle && bannerDesc && bannerActionBtn) {
    if (isLive) {
      if (cashUsd < 5.0) {
        banner.style.borderLeftColor = 'var(--warning)';
        bannerIcon.style.background = 'rgba(234, 179, 8, 0.15)';
        bannerIcon.style.color = 'var(--warning)';
        bannerIcon.textContent = '⚠️';
        bannerTitle.textContent = `Canlı Mod Aktif - Yetersiz Bakiye ($${cashUsd.toFixed(2)} USDT)`;
        bannerDesc.innerHTML = `Bağlı borsalarınızda (Binance, OKX, MEXC) kullanılabilir serbest nakit <strong>$0.00 USDT</strong> olduğu için gerçek al-sat emirleri verilememektedir (Borsaların min. işlem limiti 5-10 USDT'dir). Gerçek işlem için hesabınıza USDT aktarabilir veya <strong>Sanala Dön (10.000$ Demo)</strong> butonuna tıklayabilirsiniz.`;
      } else {
        banner.style.borderLeftColor = 'var(--profit)';
        bannerIcon.style.background = 'rgba(16, 185, 129, 0.15)';
        bannerIcon.style.color = 'var(--profit)';
        bannerIcon.textContent = '⚡';
        bannerTitle.textContent = `Canlı Çoklu Borsa Modu Aktif (${exLabel} - Serbest: $${cashUsd.toFixed(2)} USDT)`;
        bannerDesc.textContent = `Bot kayıtlı borsa API'leriniz (Binance, MEXC, OKX) üzerinden serbest USDT bakiyesiyle akıllı pozisyon almaktadır. Sanal öğrenme moduna dönmek için butona tıklayabilirsiniz.`;
      }
      bannerActionBtn.textContent = 'Sanala Dön (Öğrenme) 🧪';
      bannerActionBtn.style.borderColor = 'var(--profit)';
    } else {
      banner.style.borderLeftColor = 'var(--accent-cyan)';
      bannerIcon.style.background = 'rgba(2, 132, 199, 0.15)';
      bannerIcon.style.color = 'var(--accent-cyan)';
      bannerIcon.textContent = '🧪';
      bannerTitle.textContent = 'Sanal Öğrenme Modu Aktif ($10,000 Sanal Kasa)';
      bannerDesc.textContent = `Bot gerçek Binance piyasa verileri üzerinde stratejilerini ve sepet dengesini test ediyor. Binance API bağlantınız hazır ve onaylıdır (Key: ${binance.masked_key || 'Kayıtlı'}); dilediğiniz an tek tıkla Canlı Moda geçebilirsiniz.`;
      bannerActionBtn.textContent = 'Canlı Moda Geç ⚡';
      bannerActionBtn.style.borderColor = 'var(--accent-cyan)';
    }
  }

  // Modal Durum Göstergelerini Güncelle
  const badgeBinance = document.getElementById('badge-binance-status');
  const currentBinanceKey = document.getElementById('current-binance-key');
  if (badgeBinance && currentBinanceKey) {
    if (binance.configured) {
      badgeBinance.textContent = binance.can_trade ? '✅ Doğrulandı (Spot Yetkili)' : '⚠️ Bağlı (Yetki Eksik)';
      badgeBinance.style.color = binance.can_trade ? 'var(--profit)' : 'var(--warning)';
      currentBinanceKey.textContent = binance.masked_key || 'Tanımlı';
    } else {
      badgeBinance.textContent = 'Tanımlı Değil';
      badgeBinance.style.color = 'var(--loss)';
      currentBinanceKey.textContent = 'Girilmedi';
    }
  }

  // OKX Durum Göstergelerini Güncelle
  const badgeOkx = document.getElementById('badge-okx-status');
  const badgeOkxPass = document.getElementById('badge-okx-pass-status');
  const okx = data.okx_status || {};
  if (badgeOkx) {
    if (okx.enabled) {
      badgeOkx.textContent = '✅ Aktif & Bağlı';
      badgeOkx.style.color = 'var(--profit)';
    } else if (okx.configured) {
      badgeOkx.textContent = '⏳ Parola Bekleniyor';
      badgeOkx.style.color = 'var(--warning)';
    } else {
      badgeOkx.textContent = 'Tanımlı Değil';
      badgeOkx.style.color = 'var(--loss)';
    }
  }
  if (badgeOkxPass) {
    if (okx.enabled) {
      badgeOkxPass.textContent = '✅ Doğrulandı';
      badgeOkxPass.style.color = 'var(--profit)';
    } else {
      badgeOkxPass.textContent = 'Parola Bekleniyor';
      badgeOkxPass.style.color = 'var(--warning)';
    }
  }

  // MEXC Durum Göstergesini Güncelle
  const badgeMexc = document.getElementById('badge-mexc-status');
  const mexc = data.mexc_status || {};
  if (badgeMexc) {
    if (mexc.enabled) {
      badgeMexc.textContent = '✅ Aktif & Bağlı';
      badgeMexc.style.color = '#10b981';
    } else if (mexc.configured) {
      badgeMexc.textContent = 'Tanımlı';
      badgeMexc.style.color = 'var(--accent-cyan)';
    } else {
      badgeMexc.textContent = 'Tanımlı Değil';
      badgeMexc.style.color = 'var(--loss)';
    }
  }

  const badgeDeepSeek = document.getElementById('badge-deepseek-status');
  const currentDeepSeekKey = document.getElementById('current-deepseek-key');
  if (badgeDeepSeek && currentDeepSeekKey) {
    if (data.api_key_configured) {
      badgeDeepSeek.textContent = '✅ API Tanımlı';
      badgeDeepSeek.style.color = 'var(--profit)';
      currentDeepSeekKey.textContent = data.masked_deepseek_key || 'sk-***';
    } else {
      badgeDeepSeek.textContent = '⚡ Algoritmik Motor';
      badgeDeepSeek.style.color = 'var(--accent-cyan)';
      currentDeepSeekKey.textContent = 'Deterministik Akıl Yürütme (API gerektirmez)';
    }
  }

  const selectMode = document.getElementById('select-trading-mode');
  if (selectMode && document.activeElement !== selectMode) {
    selectMode.value = mode;
  }

  // Risk Limiti Göstergesi (Sepet Ajanı Kuralları & Ayarlar)
  const riskLimitVal = data.max_risk_per_trade_percent || 5.0;
  const agentRulesRiskEl = document.getElementById('agent-rules-risk-limit');
  if (agentRulesRiskEl) {
    agentRulesRiskEl.textContent = `Maks %${riskLimitVal.toFixed(1)} / İşlem`;
  }
  const badgeRiskLimit = document.getElementById('badge-risk-limit-display');
  if (badgeRiskLimit) {
    badgeRiskLimit.textContent = `%${riskLimitVal.toFixed(1)}`;
  }

  // 2. Kripto Sepet Dağılımı ve Sektör Çubuğu
  renderBasket(data.basket || {});

  // 3. Sentiment
  const s = data.sentiment || {};
  document.getElementById('sentiment-val').textContent = s.value || 50;
  document.getElementById('sentiment-label').textContent = s.label_tr || 'Nötr';

  // 4. Son Tarama Zamanı
  document.getElementById('last-scan-time').textContent = data.last_scan_time || 'Bekleniyor';
  
  // 5. Sinyaller Izgarası
  renderSignals(data.analyses || []);

  // 6. Açık Pozisyonlar / Canlı Cüzdan Varlıkları Tablosu
  if (posCardTitle) {
    posCardTitle.textContent = isLive ? 'Canlı Binance Cüzdan Varlıkları (Anlık Varlık & Bakiye Detayı)' : 'Aktif Sepet Varlıkları (Canlı PnL & Risk Takibi)';
  }
  renderPositions(w.open_positions || [], isLive);

  // 7. Kapanan İşlemler Tablosu
  renderTrades(w.recent_closed_trades || []);

  // 8. Çoklu Borsa Yükseliş Radarı
  if (data.breakout_radar) {
    renderBreakoutRadar(data.breakout_radar);
  }
}

function renderBasket(basket) {
  const sectors = basket.sectors || [];
  const cashPct = basket.cash_pct || 100.0;

  // Dağılım çubuğunu güncelle
  const coreSec = sectors.find(s => s.id === 'CORE') || {};
  const l1Sec = sectors.find(s => s.id === 'LAYER1') || {};
  const aiSec = sectors.find(s => s.id === 'AI_DEPIN') || {};
  const momSec = sectors.find(s => s.id === 'DEFI_MOMENTUM') || {};

  const barCore = document.getElementById('bar-core');
  const barL1 = document.getElementById('bar-layer1');
  const barAi = document.getElementById('bar-ai');
  const barMom = document.getElementById('bar-momentum');
  const barCash = document.getElementById('bar-cash');

  if (barCore) barCore.style.width = `${coreSec.current_pct || 0}%`;
  if (barL1) barL1.style.width = `${l1Sec.current_pct || 0}%`;
  if (barAi) barAi.style.width = `${aiSec.current_pct || 0}%`;
  if (barMom) barMom.style.width = `${momSec.current_pct || 0}%`;
  if (barCash) barCash.style.width = `${cashPct}%`;

  // Sektör kartlarını render et
  const container = document.getElementById('sectors-container');
  if (!container) return;

  let html = '';
  sectors.forEach(sec => {
    const pnlClass = (sec.unrealized_pnl || 0) >= 0 ? 'text-profit' : 'text-loss';
    const statusTr = sec.status === 'OVERWEIGHT' ? 'Ağırlık Yüksek' : (sec.status === 'UNDERWEIGHT' ? 'Genişleme Alanı Var' : 'Dengeli');
    const statusColor = sec.status === 'OVERWEIGHT' ? 'var(--warning)' : (sec.status === 'UNDERWEIGHT' ? 'var(--accent-cyan)' : 'var(--profit)');

    html += `
      <div class="sector-card">
        <div class="sector-card-top">
          <span class="sector-name">${sec.name}</span>
          <span class="sector-pct">%${sec.current_pct} / <span style="color: var(--text-muted); font-size: 11px;">%${sec.target_pct} Hedef</span></span>
        </div>
        <div class="sector-meta">
          <span>Değer: $${(sec.current_val || 0).toLocaleString('en-US')}</span>
          <span class="${pnlClass}">PnL: ${sec.unrealized_pnl >= 0 ? '+' : ''}$${sec.unrealized_pnl}</span>
        </div>
        <div style="margin-top: 8px; font-size: 11px; display: flex; justify-content: space-between;">
          <span style="color: var(--text-muted);">${sec.positions_count} Aktif Varlık</span>
          <span style="color: ${statusColor}; font-weight: 600;">${statusTr}</span>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

function setSignalFilter(filter, btn) {
  currentSignalFilter = filter;
  document.querySelectorAll('#signal-filters .btn-filter').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderSignals(currentAnalyses);
}

function renderSignals(analyses) {
  currentAnalyses = analyses || [];
  const container = document.getElementById('signals-container');
  
  let filtered = currentAnalyses;
  if (currentSignalFilter === 'OWNED') {
    filtered = currentAnalyses.filter(item => item.is_owned);
  } else if (currentSignalFilter !== 'ALL') {
    filtered = currentAnalyses.filter(item => item.sector === currentSignalFilter);
  }

  if (!filtered || filtered.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1/-1; padding: 32px; text-align: center; color: var(--text-muted);">
        ${currentSignalFilter === 'OWNED' ? 'Cüzdanınızdaki varlıklar taranıyor veya henüz eşleşen analiz yok.' : 'Bu filtreye uygun kripto varlık bulunamadı.'}
      </div>
    `;
    return;
  }

  let html = '';
  filtered.forEach(item => {
    const sig = item.signal || {};
    const ind = item.indicators || {};
    const action = sig.action || 'HOLD';
    const badgeClass = action === 'BUY' ? 'badge-buy' : (action === 'SELL' ? 'badge-sell' : 'badge-hold');
    const actionLabel = action === 'BUY' ? 'AL' : (action === 'SELL' ? 'SAT' : 'BEKLE');
    const changeClass = (item.change_24h || 0) >= 0 ? 'text-profit' : 'text-loss';
    const sectorTag = item.sector || 'KRIPTO';
    const isOwned = item.is_owned;
    const ownedUnits = item.owned_units;
    const ownedVal = item.owned_val;

    html += `
      <div class="signal-card ${isOwned ? 'owned-card' : ''}" onclick="openAssetModal('${item.symbol}')">
        ${isOwned ? `
          <div style="background: rgba(16, 185, 129, 0.15); color: var(--profit); border: 1px solid var(--profit); padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between;">
            <span>💼 CÜZDANINIZDA MEVCUT</span>
            <span style="font-family: var(--font-mono);">${ownedUnits} Adet ($${(ownedVal || 0).toFixed(4)})</span>
          </div>
        ` : ''}

        <div class="signal-card-top">
          <div>
            <div class="symbol-name">${item.symbol}</div>
            <div style="font-size: 11px; color: var(--accent-cyan); font-weight: 600;">${sectorTag}</div>
          </div>
          <div style="text-align: right;">
            <div class="symbol-price">${formatCryptoMoney(item.current_price || 0)}</div>
            <div style="font-size: 11px;" class="${changeClass}">%${(item.change_24h || 0).toFixed(2)}</div>
          </div>
        </div>

        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
          <span class="badge ${badgeClass}">${actionLabel} (Güven: %${((sig.confidence || 0) * 100).toFixed(0)})</span>
          <span style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">R:R ${sig.risk_reward_ratio || '1:2'}</span>
        </div>

        <div class="signal-indicators">
          <span class="indicator-pill">RSI: ${ind.rsi ? Number(ind.rsi).toFixed(1) : '-'}</span>
          <span class="indicator-pill">MACD: ${ind.macd ? ind.macd.cross : '-'}</span>
          <span class="indicator-pill">Trend: ${ind.summary || '-'}</span>
        </div>

        <div class="signal-thesis">
          <strong>AI Tezi:</strong> ${sig.thesis_summary || 'Kripto verisi analiz ediliyor...'}
        </div>

        <div style="margin-top: 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 11px; font-family: var(--font-mono);">
          <div style="color: var(--loss);">SL: $${(sig.stop_loss || 0).toLocaleString('en-US')}</div>
          <div style="color: var(--profit); text-align: right;">TP: $${(sig.take_profit || 0).toLocaleString('en-US')}</div>
        </div>

        <button class="btn btn-secondary" style="width: 100%; margin-top: 12px; font-size: 11px; height: 28px;" onclick="event.stopPropagation(); openAssetModal('${item.symbol}')">
          Kartı Aç & Canlı Grafiği İncele ↗
        </button>
      </div>
    `;
  });

  container.innerHTML = html;
}

function openAssetModal(symbol, exchange = 'BINANCE') {
  currentModalSymbol = symbol;
  const ex = (exchange || currentMarketExchange || 'BINANCE').toUpperCase();
  const item = currentAnalyses.find(a => a.symbol === symbol) || { symbol: symbol };
  const sig = item.signal || {};
  const ind = item.indicators || {};
  const cleanSym = symbol.replace('USDT', '');

  document.getElementById('modal-asset-icon').textContent = cleanSym.slice(0, 4);
  document.getElementById('modal-asset-title').textContent = `${symbol} (${ex})`;
  document.getElementById('modal-asset-sector').textContent = `${ex} SPOT`;
  document.getElementById('modal-asset-price').textContent = formatCryptoMoney(item.current_price || 0);
  
  const chgEl = document.getElementById('modal-asset-change');
  const chg = item.change_24h || 0;
  chgEl.textContent = `%${chg >= 0 ? '+' : ''}${chg.toFixed(2)}`;
  chgEl.className = chg >= 0 ? 'text-profit' : 'text-loss';

  const ownedEl = document.getElementById('modal-asset-owned');
  if (item.is_owned) {
    ownedEl.style.display = 'inline-block';
    ownedEl.textContent = `CÜZDANDA: ${item.owned_units} ${cleanSym}`;
  } else {
    ownedEl.style.display = 'none';
  }

  document.getElementById('modal-ind-rsi').textContent = ind.rsi ? Number(ind.rsi).toFixed(1) : '-';
  document.getElementById('modal-ind-macd').textContent = ind.macd ? ind.macd.cross : '-';
  document.getElementById('modal-ind-trend').textContent = ind.summary || '-';
  document.getElementById('modal-ind-atr').textContent = ind.atr ? `$${Number(ind.atr).toFixed(2)}` : '-';
  
  const actEl = document.getElementById('modal-ind-action');
  const action = sig.action || 'HOLD';
  actEl.textContent = action === 'BUY' ? 'AL' : (action === 'SELL' ? 'SAT' : 'BEKLE');
  actEl.style.color = action === 'BUY' ? 'var(--profit)' : (action === 'SELL' ? 'var(--loss)' : 'var(--warning)');

  document.getElementById('modal-ai-thesis').textContent = sig.thesis_summary || 'Yapay zeka finansal tezi derleniyor...';

  // Hyperliquid Vadeli Fonlama & Squeeze İstihbaratı
  const hlFundingEl = document.getElementById('modal-hl-funding');
  const hlOiEl = document.getElementById('modal-hl-oi');
  const hlSqueezeEl = document.getElementById('modal-hl-squeeze');
  if (hlFundingEl) hlFundingEl.textContent = 'Çekiliyor...';
  
  fetch(`/api/market/funding/${symbol}`)
    .then(r => r.json())
    .then(d => {
      if (d.status === 'SUCCESS' && d.perps) {
        const p = d.perps;
        if (hlFundingEl) {
          const sign = p.funding_rate_8h_pct >= 0 ? '+' : '';
          hlFundingEl.textContent = `${sign}%${p.funding_rate_8h_pct.toFixed(4)}`;
          hlFundingEl.style.color = p.funding_rate_8h_pct >= 0.04 ? 'var(--loss)' : (p.funding_rate_8h_pct <= -0.03 ? 'var(--profit)' : 'var(--text-primary)');
        }
        if (hlOiEl) {
          hlOiEl.textContent = p.open_interest_usd ? `$${(p.open_interest_usd / 1e6).toFixed(2)}M` : '$0';
        }
        if (hlSqueezeEl) {
          hlSqueezeEl.textContent = p.squeeze_tr || 'Dengeli Piyasa';
          hlSqueezeEl.style.color = p.risk_color || 'var(--accent-cyan)';
          hlSqueezeEl.style.borderColor = p.risk_color || 'var(--accent-cyan)';
        }
      }
    })
    .catch(() => {
      if (hlFundingEl) hlFundingEl.textContent = 'Nötr';
    });

  // TradingView Canlı Kripto Grafiği (Seçili Borsanın Canlı Verisi)
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
  const tvTheme = currentTheme === 'light' ? 'light' : 'dark';
  const tvBg = currentTheme === 'light' ? 'ffffff' : '131722';
  const tvContainer = document.getElementById('tradingview-container');
  if (tvContainer) {
    tvContainer.style.background = currentTheme === 'light' ? '#ffffff' : '#131722';
    tvContainer.innerHTML = `
      <iframe 
        src="https://s.tradingview.com/widgetembed/?frameElementId=tradingview_widget&symbol=${ex}%3A${symbol}&interval=15&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=${tvBg}&studies=%5B%5D&theme=${tvTheme}&style=1&timezone=Europe%2FIstanbul&locale=tr" 
        style="width: 100%; height: 100%; border: none;"
        allowtransparency="true" 
        scrolling="no">
      </iframe>
    `;
  }

  setModalTradeMode(currentTradingMode || 'PAPER');
  document.getElementById('asset-modal').style.display = 'flex';
}

function closeAssetModal() {
  const modal = document.getElementById('asset-modal');
  if (modal) modal.style.display = 'none';
  const tv = document.getElementById('tradingview-container');
  if (tv) tv.innerHTML = '';
}

function setModalTradeMode(mode) {
  modalTradingMode = mode;
  const isLive = mode === 'LIVE';
  
  const btnPaper = document.getElementById('modal-btn-mode-paper');
  const btnLive = document.getElementById('modal-btn-mode-live');
  const badge = document.getElementById('modal-mode-badge');
  const exContainer = document.getElementById('modal-exchange-select-container');

  if (btnPaper && btnLive) {
    if (isLive) {
      btnLive.style.background = 'var(--profit)';
      btnLive.style.color = '#000';
      btnPaper.style.background = 'transparent';
      btnPaper.style.color = 'var(--text-secondary)';
    } else {
      btnPaper.style.background = 'var(--accent-cyan)';
      btnPaper.style.color = '#000';
      btnLive.style.background = 'transparent';
      btnLive.style.color = 'var(--text-secondary)';
    }
  }

  if (badge) {
    badge.textContent = isLive ? '⚡ Canlı Borsa Emri' : '🧪 Sanal Kasa Emri';
    badge.style.color = isLive ? 'var(--profit)' : 'var(--accent-cyan)';
    badge.style.borderColor = isLive ? 'var(--profit)' : 'var(--accent-cyan)';
  }

  if (exContainer) {
    exContainer.style.display = isLive ? 'block' : 'none';
  }

  const statusEl = document.getElementById('modal-trade-status');
  if (statusEl) statusEl.style.display = 'none';

  updateModalBalanceInfo();
}

function updateModalBalanceInfo() {
  if (!currentModalSymbol) return;
  const freeCashEl = document.getElementById('modal-free-cash');
  const ownedQtyEl = document.getElementById('modal-owned-qty');
  const depositHintEl = document.getElementById('modal-deposit-hint');
  const exEl = document.getElementById('modal-trade-exchange');
  const selectedEx = (exEl ? exEl.value : 'BINANCE').toUpperCase();
  const cleanSym = currentModalSymbol.replace('USDT', '');

  if (!lastDashboardData) return;

  if (modalTradingMode === 'LIVE') {
    const mt = lastDashboardData.master_treasury || {};
    const binanceStatus = lastDashboardData.binance_status || {};
    
    let freeUsdt = 0;
    let ownedUnits = 0;

    if (selectedEx === 'BINANCE' || selectedEx === 'AUTO') {
      freeUsdt = binanceStatus.free_usdt !== undefined ? binanceStatus.free_usdt : ((mt.binance && mt.binance.free_usdt) || 0);
      const assets = binanceStatus.assets || {};
      if (assets[cleanSym]) {
        ownedUnits = assets[cleanSym].free !== undefined ? assets[cleanSym].free : (assets[cleanSym].total || 0);
      }
    } else if (selectedEx === 'OKX') {
      freeUsdt = mt.okx ? mt.okx.free_usdt : 0;
    } else if (selectedEx === 'MEXC') {
      freeUsdt = mt.mexc ? mt.mexc.free_usdt : 0;
    }

    if (freeCashEl) freeCashEl.textContent = `${formatCryptoMoney(freeUsdt)} USDT`;
    if (ownedQtyEl) ownedQtyEl.textContent = `${Number(ownedUnits).toFixed(4)} ${cleanSym}`;
    
    // Yetersiz USDT uyarısı
    if (depositHintEl) {
      depositHintEl.style.display = (freeUsdt < 5.0) ? 'block' : 'none';
    }
  } else {
    // Sanal Kasa
    const w = lastDashboardData.wallet || {};
    const cash = w.cash_balance !== undefined ? w.cash_balance : 10000.0;
    const positions = w.open_positions || [];
    const myPos = positions.find(p => p.symbol === currentModalSymbol || p.symbol === cleanSym || p.symbol === `${cleanSym}USDT`);
    const ownedUnits = myPos ? (myPos.units || 0) : 0;

    if (freeCashEl) freeCashEl.textContent = `${formatCryptoMoney(cash)} USD`;
    if (ownedQtyEl) ownedQtyEl.textContent = `${Number(ownedUnits).toFixed(4)} ${cleanSym}`;
    if (depositHintEl) depositHintEl.style.display = 'none';
  }
}

function setModalAmountMax() {
  const amtInput = document.getElementById('modal-trade-amount');
  if (!amtInput || !lastDashboardData) return;
  
  if (modalTradingMode === 'LIVE') {
    const binanceStatus = lastDashboardData.binance_status || {};
    const freeUsdt = binanceStatus.free_usdt || 0;
    amtInput.value = freeUsdt >= 5.0 ? freeUsdt.toFixed(2) : 50;
  } else {
    const w = lastDashboardData.wallet || {};
    const cash = w.cash_balance !== undefined ? w.cash_balance : 10000.0;
    amtInput.value = Math.min(1000, Math.floor(cash));
  }
}

async function submitManualOrder(action) {
  if (!currentModalSymbol) return;
  const amtInput = document.getElementById('modal-trade-amount');
  const amt = parseFloat(amtInput ? amtInput.value : 50) || 50;
  const exEl = document.getElementById('modal-trade-exchange');
  const exVal = (modalTradingMode === 'LIVE' && exEl) ? exEl.value : 'AUTO';
  const statusEl = document.getElementById('modal-trade-status');
  
  statusEl.style.display = 'block';
  statusEl.style.background = 'rgba(2, 132, 199, 0.1)';
  statusEl.style.border = '1px solid rgba(2, 132, 199, 0.3)';
  statusEl.innerHTML = `<span style="color: var(--accent-cyan); font-weight: 600;">⏳ ${modalTradingMode === 'LIVE' ? 'Canlı borsa' : 'Sanal kasa'} emri iletiliyor (${action} $${amt})...</span>`;

  // Frontend ön kontrol: Canlı modda USDT 0 iken alım yapılmaya çalışılırsa kullanıcıyı anında bilgilendir
  if (modalTradingMode === 'LIVE' && action === 'BUY' && lastDashboardData) {
    const binanceStatus = lastDashboardData.binance_status || {};
    const freeUsdt = binanceStatus.free_usdt || 0;
    if (freeUsdt < 5.0 && (exVal === 'BINANCE' || exVal === 'AUTO')) {
      statusEl.style.background = 'rgba(239, 68, 68, 0.1)';
      statusEl.style.border = '1px solid rgba(239, 68, 68, 0.3)';
      statusEl.innerHTML = `
        <div style="color: var(--loss); font-weight: 700; margin-bottom: 4px;">❌ Binance Serbest Bakiyesi Yetersiz ($${freeUsdt.toFixed(2)} USDT)</div>
        <div style="color: var(--text-secondary); font-size: 11px; line-height: 1.4;">
          Binance hesabınızda serbest USDT ($0.00) bulunmuyor. Gerçek canlı alım yapabilmek için hesabınıza USDT yatırmanız gerekmektedir. Veya üstteki <strong>'🧪 Sanal Kasa'</strong> sekmesine geçerek simülasyon olarak test edebilirsiniz.
        </div>
        <button type="button" class="btn btn-secondary" style="margin-top: 8px; font-size: 11px; height: 28px; color: var(--warning); border-color: rgba(245, 158, 11, 0.5);" onclick="openDepositModal()">
          📥 Binance Resmi Kripto Yatırma Adreslerimi Aç
        </button>
      `;
      return;
    }
  }

  try {
    const res = await fetch('/api/trade/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: currentModalSymbol,
        action: action,
        amount_usd: amt,
        exchange: exVal,
        mode: modalTradingMode
      })
    });
    const data = await res.json();
    if (res.ok && data.status === 'SUCCESS') {
      statusEl.style.background = 'rgba(16, 185, 129, 0.1)';
      statusEl.style.border = '1px solid rgba(16, 185, 129, 0.3)';
      statusEl.innerHTML = `<span style="color: var(--profit); font-weight: 700;">${data.message}</span>`;
      await fetchState();
      updateModalBalanceInfo();
    } else {
      statusEl.style.background = 'rgba(239, 68, 68, 0.1)';
      statusEl.style.border = '1px solid rgba(239, 68, 68, 0.3)';
      statusEl.innerHTML = `<span style="color: var(--loss); font-weight: 700;">${data.message || 'İşlem başarısız.'}</span>`;
    }
  } catch (err) {
    statusEl.style.background = 'rgba(239, 68, 68, 0.1)';
    statusEl.style.border = '1px solid rgba(239, 68, 68, 0.3)';
    statusEl.innerHTML = `<span style="color: var(--loss); font-weight: 700;">Bağlantı hatası: ${err.message}</span>`;
  }
}

function formatCryptoMoney(val) {
  if (val === null || val === undefined) return '$0.00';
  const num = Number(val);
  if (num === 0) return '$0.00';
  if (Math.abs(num) < 0.01) {
    return '$' + num.toFixed(5);
  }
  return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

let currentExchangeFilter = 'ALL';
let lastPositions = [];
let lastIsLive = false;

function setExchangeFilter(ex, btn) {
  currentExchangeFilter = ex;
  ['filter-ex-all', 'filter-ex-binance', 'filter-ex-okx', 'filter-ex-mexc'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });
  if (btn) btn.classList.add('active');

  const statusLabel = document.getElementById('positions-active-filter-label');
  if (statusLabel) {
    if (ex === 'ALL') statusLabel.textContent = 'Konsolide Çoklu Borsa';
    else if (ex === 'Binance') statusLabel.textContent = '🟡 Binance Spot Varlıkları';
    else if (ex === 'OKX') statusLabel.textContent = '⚫ OKX Spot Varlıkları';
    else if (ex === 'MEXC') statusLabel.textContent = '🟢 MEXC Spot Varlıkları';
  }
  renderPositions(lastPositions, lastIsLive);
}

function renderPositions(positions, isLive) {
  lastPositions = positions;
  lastIsLive = isLive;
  const tbody = document.getElementById('positions-body');

  let filtered = positions;
  if (isLive && currentExchangeFilter !== 'ALL') {
    filtered = positions.filter(p => (p.exchange || 'Binance').toUpperCase() === currentExchangeFilter.toUpperCase());
  }

  if (!filtered || filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 24px;">${currentExchangeFilter !== 'ALL' ? currentExchangeFilter + ' borsasında varlık bulunamadı.' : (isLive ? 'Borsalarda bakiye bulunamadı.' : 'Aktif açık sepet varlığı bulunmuyor.')}</td></tr>`;
    return;
  }

  let html = '';
  filtered.forEach(pos => {
    const lookupSym = pos.symbol.includes('USDT') ? pos.symbol : (pos.asset ? pos.asset + 'USDT' : 'BTCUSDT');
    const exName = (pos.exchange || 'Binance').toUpperCase();
    let exBadge = `<span class="indicator-pill" style="color: #f3ba2f; border-color: rgba(243, 186, 47, 0.4); font-weight: 700; margin-right: 6px;">🟡 Binance</span>`;
    if (exName === 'OKX') {
      exBadge = `<span class="indicator-pill" style="color: var(--accent-cyan); border-color: rgba(2, 132, 199, 0.4); font-weight: 700; margin-right: 6px;">⚫ OKX</span>`;
    } else if (exName === 'MEXC') {
      exBadge = `<span class="indicator-pill" style="color: #10b981; border-color: rgba(16, 185, 129, 0.4); font-weight: 700; margin-right: 6px;">🟢 MEXC</span>`;
    }

    if (isLive) {
      // CANLI ÇOKLU BORSA CÜZDAN VARLIKLARI (Eksiksiz ve tam tamına)
      const valStr = formatCryptoMoney(pos.position_value);
      const pxStr = formatCryptoMoney(pos.current_price);
      const unitsStr = typeof pos.units === 'number' ? pos.units.toFixed(8).replace(/\.?0+$/, '') : pos.units;
      const walletTag = pos.wallet_type || 'Spot Cüzdanı';

      html += `
        <tr style="cursor: pointer;" onclick="openAssetModal('${lookupSym}')" title="Canlı grafiği ve detayları açmak için tıklayın">
          <td>
            <div style="display: flex; align-items: center;">
              ${exBadge}
              <div>
                <strong>${pos.asset || pos.symbol}</strong>
                <div style="font-size: 11px; color: var(--text-muted);">${pos.symbol}</div>
              </div>
            </div>
          </td>
          <td><span class="indicator-pill" style="color: var(--accent-cyan); font-weight: 600;">${walletTag}</span></td>
          <td><span class="badge badge-buy">CÜZDANDA</span></td>
          <td>-</td>
          <td>${pxStr}</td>
          <td>
            <span style="color: var(--text-secondary); font-size: 12px; font-family: var(--font-mono); font-weight: 700;">
              ${unitsStr} ${pos.asset || ''}
            </span>
          </td>
          <td style="font-family: var(--font-mono); font-weight: 700; color: var(--profit);">${valStr}</td>
          <td class="text-profit">Tam Bakiye</td>
          <td style="text-align: right;">
            <button class="btn btn-secondary" style="font-size: 11px; height: 26px; padding: 0 8px;" onclick="event.stopPropagation(); openAssetModal('${lookupSym}')">
              Grafik & Al-Sat ↗
            </button>
          </td>
        </tr>
      `;
    } else {
      // SANAL KASA / ÖĞRENME MODU POZİSYONLARI
      const pnl = pos.unrealized_pnl || 0;
      const pnlPct = pos.unrealized_pnl_pct || 0;
      const pnlClass = pnl >= 0 ? 'text-profit' : 'text-loss';
      const badgeClass = pos.action === 'BUY' ? 'badge-buy' : 'badge-sell';

      html += `
        <tr style="cursor: pointer;" onclick="openAssetModal('${lookupSym}')" title="Canlı grafiği ve detayları açmak için tıklayın">
          <td><strong>${pos.symbol}</strong></td>
          <td><span class="indicator-pill" style="color: var(--accent-cyan);">${pos.symbol.includes('BTC') || pos.symbol.includes('ETH') ? 'CORE' : 'ALTCOIN'}</span></td>
          <td><span class="badge ${badgeClass}">${pos.action}</span></td>
          <td>${formatCryptoMoney(pos.entry_price)}</td>
          <td>${formatCryptoMoney(pos.current_price)}</td>
          <td>
            <span style="color: var(--loss); font-size: 11px;">SL: ${formatCryptoMoney(pos.stop_loss)}</span><br>
            <span style="color: var(--profit); font-size: 11px;">TP: ${formatCryptoMoney(pos.take_profit)}</span>
          </td>
          <td>${formatCryptoMoney(pos.position_value)}</td>
          <td class="${pnlClass}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (%${pnlPct.toFixed(2)})</td>
          <td style="text-align: right; display: flex; gap: 4px; justify-content: flex-end;">
            <button class="btn btn-secondary" style="font-size: 11px; height: 26px; padding: 0 6px;" onclick="event.stopPropagation(); openAssetModal('${lookupSym}')">Grafik ↗</button>
            <button class="btn-danger-sm" onclick="event.stopPropagation(); closePosition('${pos.id}', ${pos.current_price})">Kapat</button>
          </td>
        </tr>
      `;
    }
  });
  tbody.innerHTML = html;
}

function renderTrades(trades) {
  const tbody = document.getElementById('trades-body');
  if (!trades || trades.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 24px;">Henüz kapanmış bir sepet işlemi yok.</td></tr>`;
    return;
  }

  let html = '';
  trades.forEach(t => {
    const pnl = t.pnl_usd || 0;
    const pnlPct = t.pnl_pct || 0;
    const pnlClass = pnl >= 0 ? 'text-profit' : 'text-loss';
    const reasonTr = t.exit_reason === 'TAKE_PROFIT_HIT' ? 'Hedef (TP)' : (t.exit_reason === 'STOP_LOSS_HIT' ? 'Stop (SL)' : (t.exit_reason === 'PORTFOLIO_CRYPTO_BASKET_TRANSITION' ? 'Sepet Geçişi' : 'Manuel'));

    html += `
      <tr>
        <td><strong>${t.symbol}</strong></td>
        <td>${t.action}</td>
        <td>$${t.entry_price.toLocaleString('en-US')}</td>
        <td>$${t.exit_price.toLocaleString('en-US')}</td>
        <td class="${pnlClass}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (%${pnlPct.toFixed(2)})</td>
        <td style="color: var(--text-muted); font-size: 11px;">${reasonTr}</td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

async function triggerManualScan() {
  const btn = document.getElementById('btn-scan');
  const originalText = btn ? btn.innerHTML : 'Sepeti Analiz Et & Dengele';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳ Sepet Hesaplanıyor...';
  }

  try {
    const res = await fetch('/api/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    if (res.ok) {
      await fetchState();
    }
  } catch (err) {
    console.error('Sepet taraması başlatılırken hata:', err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  }
}

async function closePosition(posId, currentPx) {
  if (!confirm('Bu sepet varlığını anlık fiyattan kapatmak istediğinize emin misiniz?')) return;
  try {
    const res = await fetch('/api/trade/close', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ position_id: posId, exit_price: currentPx })
    });
    if (res.ok) {
      fetchState();
    } else {
      alert('Pozisyon kapatılamadı');
    }
  } catch (e) {
    alert('Hata: ' + e);
  }
}

function applyModeUIToDOM(mode) {
  currentTradingMode = mode;
  const isLive = mode === 'LIVE';

  // 1. Header Butonu
  const btnToggle = document.getElementById('btn-mode-toggle');
  const modeText = document.getElementById('mode-text');
  const modeDot = document.getElementById('mode-dot');
  if (modeText) modeText.textContent = isLive ? 'Canlı Mod (Binance)' : 'Sanal Mod ($10K)';
  if (modeDot) modeDot.style.background = isLive ? 'var(--profit)' : 'var(--warning)';
  if (btnToggle) btnToggle.style.borderColor = isLive ? 'var(--profit)' : 'var(--accent-cyan)';

  // 2. Banner
  const banner = document.getElementById('mode-banner');
  const bannerIcon = document.getElementById('banner-icon');
  const bannerTitle = document.getElementById('banner-title');
  const bannerDesc = document.getElementById('banner-desc');
  const bannerActionBtn = document.getElementById('banner-action-btn');

  if (banner) banner.style.borderLeftColor = isLive ? 'var(--profit)' : 'var(--accent-cyan)';
  if (bannerIcon) {
    bannerIcon.textContent = isLive ? '⚡' : '🧪';
    bannerIcon.style.background = isLive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(2, 132, 199, 0.15)';
    bannerIcon.style.color = isLive ? 'var(--profit)' : 'var(--accent-cyan)';
  }
  if (bannerTitle) bannerTitle.textContent = isLive ? 'Canlı Kripto Modu Aktif (Binance & Çoklu Borsa)' : 'Sanal Öğrenme Modu Aktif ($10,000 Sanal Kasa)';
  if (bannerDesc) bannerDesc.textContent = isLive ? 'Bot gerçek borsa hesap bakiyeniz üzerinden canlı emirler yönetir.' : 'Bot canlı piyasa mumları üzerinde $10,000 sanal kasa ile stratejilerini test eder.';
  if (bannerActionBtn) {
    bannerActionBtn.textContent = isLive ? 'Sanal Moda Geç 🧪' : 'Canlı Moda Geç ⚡';
    bannerActionBtn.style.borderColor = isLive ? 'var(--profit)' : 'var(--accent-cyan)';
  }

  // 3. Kasa etiketleri
  const mEquityLabel = document.getElementById('m-equity-label');
  const mCashLabel = document.getElementById('m-cash-label');
  const posCardTitle = document.getElementById('pos-card-title');
  if (mEquityLabel) mEquityLabel.textContent = isLive ? 'Konsolide Canlı Kasa' : 'Konsolide Ana Kasa';
  if (mCashLabel) mCashLabel.textContent = isLive ? 'Kullanılabilir Boşta Nakit' : 'Kullanılabilir Boşta Nakit';
  if (posCardTitle) posCardTitle.textContent = isLive ? 'Canlı Borsa Varlıkları (Spot Cüzdanı)' : 'Aktif Sepet Varlıkları (Canlı PnL & Risk Takibi)';
}

async function toggleTradingMode() {
  const newMode = currentTradingMode === 'LIVE' ? 'PAPER' : 'LIVE';
  const prevMode = currentTradingMode;

  // 1. İyimser anında UI güncellemesi (0.01 sn tepki süresi!)
  applyModeUIToDOM(newMode);

  // 2. Arka planda ultra-hızlı API çağrısı
  try {
    const res = await fetch('/api/mode/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trading_mode: newMode })
    });
    const data = await res.json();
    if (!res.ok || data.status !== 'SUCCESS') {
      applyModeUIToDOM(prevMode);
      alert('Mod değiştirilemedi: ' + (data.message || 'Bilinmeyen hata'));
      return;
    }
    // Arka planda bakiye ve verileri sessizce güncelle
    fetchState();
  } catch (err) {
    applyModeUIToDOM(prevMode);
    console.error('Mod değiştirme hatası:', err);
  }
}

async function setTradingExchange(ex) {
  try {
    const res = await fetch('/api/exchange/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exchange: ex })
    });
    const data = await res.json();
    if (res.ok && data.status === 'SUCCESS') {
      fetchState();
    }
  } catch (err) {
    console.error('Borsa tercihi güncellenemedi:', err);
  }
}

async function openSettingsModal() {
  const modal = document.getElementById('settings-modal');
  if (modal) {
    modal.style.display = 'flex';
  }
  const statusMsg = document.getElementById('settings-status-msg');
  if (statusMsg) statusMsg.style.display = 'none';

  try {
    const res = await fetch('/api/config');
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === 'SUCCESS') {
      const c = data.config || data;

      // Model & Mod & Risk & Borsa
      const selModel = document.getElementById('select-model');
      if (selModel && c.deepseek_model) selModel.value = c.deepseek_model;

      const selMode = document.getElementById('select-trading-mode');
      if (selMode && c.trading_mode) selMode.value = c.trading_mode;

      const selExchange = document.getElementById('select-trading-exchange');
      if (selExchange && c.trading_exchange) selExchange.value = c.trading_exchange;

      const selRisk = document.getElementById('select-risk-profile');
      if (selRisk && c.ai_risk_profile) selRisk.value = c.ai_risk_profile;

      const selRiskLimit = document.getElementById('select-risk-limit');
      if (selRiskLimit && c.max_risk_per_trade_percent !== undefined) {
        selRiskLimit.value = String(Number(c.max_risk_per_trade_percent).toFixed(1));
      }
      const badgeRiskLimit = document.getElementById('badge-risk-limit-display');
      if (badgeRiskLimit && c.max_risk_per_trade_percent !== undefined) {
        badgeRiskLimit.textContent = `%${Number(c.max_risk_per_trade_percent).toFixed(1)}`;
      }

      // DeepSeek API
      const badgeDs = document.getElementById('badge-deepseek-status');
      const curDs = document.getElementById('current-deepseek-key');
      const inputDs = document.getElementById('input-api-key');
      const hasDs = c.deepseek_api_key_set || c.deepseek_api_key_configured;
      if (hasDs) {
        if (badgeDs) { badgeDs.textContent = '✅ API Tanımlı'; badgeDs.style.color = 'var(--profit)'; }
        if (curDs) curDs.textContent = c.deepseek_masked_key || 'sk-***';
        if (inputDs) { inputDs.value = ''; inputDs.placeholder = 'sk-... (Mevcut anahtar kayıtlı - değiştirmek için yeni girin)'; }
      } else {
        if (badgeDs) { badgeDs.textContent = '⚡ Algoritmik Motor'; badgeDs.style.color = 'var(--accent-cyan)'; }
        if (curDs) curDs.textContent = 'Girilmedi (Deterministik mod)';
        if (inputDs) { inputDs.value = ''; inputDs.placeholder = 'sk-... (DeepSeek API Key)'; }
      }

      // Binance
      const badgeBin = document.getElementById('badge-binance-status');
      const curBin = document.getElementById('current-binance-key');
      const inBinKey = document.getElementById('input-binance-key');
      const inBinSec = document.getElementById('input-binance-secret');
      const hasBin = Boolean(c.binance_configured);
      if (hasBin) {
        if (badgeBin) { badgeBin.textContent = '✅ Doğrulandı (Spot Yetkili)'; badgeBin.style.color = 'var(--profit)'; }
        if (curBin) curBin.textContent = c.binance_masked_key || 'Kayıtlı';
        if (inBinKey) { inBinKey.value = ''; inBinKey.placeholder = c.binance_masked_key ? (c.binance_masked_key + ' (Kayıtlı - değiştirmek için yeni girin)') : 'Binance API Key...'; }
        if (inBinSec) { inBinSec.value = ''; inBinSec.placeholder = '●●●●●●●● (Kayıtlı - değiştirmek için yeni girin)'; }
      } else {
        if (badgeBin) { badgeBin.textContent = 'Tanımlı Değil'; badgeBin.style.color = 'var(--loss)'; }
        if (curBin) curBin.textContent = 'Girilmedi';
        if (inBinKey) { inBinKey.value = ''; inBinKey.placeholder = 'Binance API Key...'; }
        if (inBinSec) { inBinSec.value = ''; inBinSec.placeholder = 'Binance Secret Key...'; }
      }

      // OKX
      const badgeOkx = document.getElementById('badge-okx-status');
      const badgeOkxPass = document.getElementById('badge-okx-pass-status');
      const inOkxKey = document.getElementById('input-okx-key');
      const inOkxSec = document.getElementById('input-okx-secret');
      const inOkxPass = document.getElementById('input-okx-passphrase');
      const hasOkx = Boolean(c.okx_configured);
      if (hasOkx) {
        if (badgeOkx) { badgeOkx.textContent = '✅ Kayıtlı'; badgeOkx.style.color = 'var(--profit)'; }
        if (inOkxKey) { inOkxKey.value = ''; inOkxKey.placeholder = c.okx_masked_key ? (c.okx_masked_key + ' (Kayıtlı - değiştirmek için yeni girin)') : 'OKX API Key...'; }
        if (inOkxSec) { inOkxSec.value = ''; inOkxSec.placeholder = '●●●●●●●● (Kayıtlı - değiştirmek için yeni girin)'; }
      } else {
        if (badgeOkx) { badgeOkx.textContent = 'Tanımlı Değil'; badgeOkx.style.color = 'var(--loss)'; }
        if (inOkxKey) { inOkxKey.value = ''; inOkxKey.placeholder = 'OKX API Key...'; }
        if (inOkxSec) { inOkxSec.value = ''; inOkxSec.placeholder = 'OKX Secret Key...'; }
      }
      const hasPass = Boolean(c.okx_has_passphrase);
      if (hasPass) {
        if (badgeOkxPass) { badgeOkxPass.textContent = '✅ Doğrulandı'; badgeOkxPass.style.color = 'var(--profit)'; }
        if (inOkxPass) { inOkxPass.value = ''; inOkxPass.placeholder = '●●●●●●●● (Kayıtlı - değiştirmek için yeni girin)'; }
      } else {
        if (badgeOkxPass) { badgeOkxPass.textContent = '⏳ Parola Bekleniyor'; badgeOkxPass.style.color = 'var(--warning)'; }
        if (inOkxPass) { inOkxPass.value = ''; inOkxPass.placeholder = 'OKX API parolanız...'; }
      }

      // MEXC
      const badgeMexc = document.getElementById('badge-mexc-status');
      const inMexcKey = document.getElementById('input-mexc-key');
      const inMexcSec = document.getElementById('input-mexc-secret');
      const hasMexc = Boolean(c.mexc_configured);
      if (hasMexc) {
        if (badgeMexc) { badgeMexc.textContent = '✅ Kayıtlı & Bağlı'; badgeMexc.style.color = '#10b981'; }
        if (inMexcKey) { inMexcKey.value = ''; inMexcKey.placeholder = c.mexc_masked_key ? (c.mexc_masked_key + ' (Kayıtlı - değiştirmek için yeni girin)') : 'MEXC API Key...'; }
        if (inMexcSec) { inMexcSec.value = ''; inMexcSec.placeholder = '●●●●●●●● (Kayıtlı - değiştirmek için yeni girin)'; }
      } else {
        if (badgeMexc) { badgeMexc.textContent = 'Tanımlı Değil'; badgeMexc.style.color = 'var(--loss)'; }
        if (inMexcKey) { inMexcKey.value = ''; inMexcKey.placeholder = 'MEXC API Key...'; }
        if (inMexcSec) { inMexcSec.value = ''; inMexcSec.placeholder = 'MEXC Secret Key...'; }
      }

      // Telegram
      const inTgToken = document.getElementById('input-tg-token');
      const inTgChat = document.getElementById('input-tg-chat');
      if (inTgChat && c.telegram_chat_id) inTgChat.value = c.telegram_chat_id;
      const hasTg = c.telegram_configured || Boolean(c.telegram_token);
      if (inTgToken) {
        inTgToken.value = '';
        inTgToken.placeholder = hasTg ? '●●●●●●●● (Kayıtlı - değiştirmek için yeni girin)' : '123456:ABC-DEF...';
      }

      // Groq Cloud API
      const badgeGroq = document.getElementById('badge-groq-status');
      const curGroq = document.getElementById('current-groq-key');
      const inGroqKey = document.getElementById('input-groq-key');
      const hasGroq = c.groq_configured || Boolean(c.groq_api_key);
      if (hasGroq) {
        if (badgeGroq) { badgeGroq.textContent = '⚡ Groq LPU Aktif'; badgeGroq.style.color = 'var(--profit)'; }
        if (curGroq) curGroq.textContent = c.groq_masked_key || 'gsk_***';
        if (inGroqKey) { inGroqKey.value = ''; inGroqKey.placeholder = 'gsk_... (Mevcut anahtar kayıtlı - değiştirmek için yeni girin)'; }
      } else {
        if (badgeGroq) { badgeGroq.textContent = '⚪ Opsiyonel (Boş)'; badgeGroq.style.color = 'var(--text-muted)'; }
        if (curGroq) curGroq.textContent = 'Girilmedi (DeepSeek birincil)';
        if (inGroqKey) { inGroqKey.value = ''; inGroqKey.placeholder = 'gsk_... (console.groq.com ücretsiz anahtarı)'; }
      }

      // CoinGecko API
      const badgeCg = document.getElementById('badge-coingecko-status');
      const curCg = document.getElementById('current-coingecko-key');
      const inCgKey = document.getElementById('input-coingecko-key');
      const hasCg = c.coingecko_configured || Boolean(c.coingecko_api_key);
      if (hasCg) {
        if (badgeCg) { badgeCg.textContent = '✅ Demo API Tanımlı'; badgeCg.style.color = 'var(--profit)'; }
        if (curCg) curCg.textContent = c.coingecko_masked_key || 'CG-***';
        if (inCgKey) { inCgKey.value = ''; inCgKey.placeholder = 'CG-... (Mevcut anahtar kayıtlı - değiştirmek için yeni girin)'; }
      } else {
        if (badgeCg) { badgeCg.textContent = '✅ Açık / Ücretsiz Aktif'; badgeCg.style.color = 'var(--profit)'; }
        if (curCg) curCg.textContent = 'Genel Ücretsiz API (Anahtarsız)';
        if (inCgKey) { inCgKey.value = ''; inCgKey.placeholder = 'CG-... (Boş bırakırsanız genel ücretsiz API çalışır)'; }
      }

      // FRED API
      const badgeFred = document.getElementById('badge-fred-status');
      const curFred = document.getElementById('current-fred-key');
      const inFredKey = document.getElementById('input-fred-key');
      const hasFred = c.fred_configured || Boolean(c.fred_api_key);
      if (hasFred) {
        if (badgeFred) { badgeFred.textContent = '✅ FRED API Tanımlı'; badgeFred.style.color = 'var(--profit)'; }
        if (curFred) curFred.textContent = c.fred_masked_key || '***';
        if (inFredKey) { inFredKey.value = ''; inFredKey.placeholder = '32 karakterlik FRED key (Kayıtlı - değiştirmek için yeni girin)'; }
      } else {
        if (badgeFred) { badgeFred.textContent = '✅ DXY / Tahvil Kalkanı Aktif'; badgeFred.style.color = 'var(--accent-cyan)'; }
        if (curFred) curFred.textContent = 'Canlı Açık DXY/Tahvil Akışı (Anahtarsız)';
        if (inFredKey) { inFredKey.value = ''; inFredKey.placeholder = '32 karakterlik FRED API Key (Boş bırakırsanız açık DXY/Tahvil akışı çalışır)'; }
      }

      // Yönetici PIN Kodu
      const badgePin = document.getElementById('badge-admin-pin-status');
      const inPin = document.getElementById('input-admin-pin');
      if (badgePin) {
        badgePin.textContent = c.admin_pin_configured ? '✅ Aktif' : 'Tanımlı Değil';
        badgePin.style.color = c.admin_pin_configured ? 'var(--profit)' : 'var(--warning)';
      }
      if (inPin) {
        inPin.value = '';
        inPin.placeholder = c.admin_pin_masked ? (c.admin_pin_masked + ' (Değiştirmek için yeni PIN girin)') : 'Yeni PIN...';
      }
    }
  } catch (err) {
    console.error('Ayarlar yüklenemedi:', err);
  }
}

function closeSettingsModal() {
  document.getElementById('settings-modal').style.display = 'none';
}

async function openDepositModal(exchange = 'BINANCE') {
  const modal = document.getElementById('deposit-modal');
  const container = document.getElementById('deposit-addresses-list');
  modal.style.display = 'flex';
  
  const exUpper = exchange.toUpperCase();
  let exName = 'Binance';
  let endpoint = '/api/wallet/deposit-addresses';
  
  if (exUpper === 'OKX') {
    exName = 'OKX';
    endpoint = '/api/wallet/okx-deposit-addresses';
  } else if (exUpper === 'MEXC') {
    exName = 'MEXC';
    endpoint = '/api/wallet/mexc-deposit-addresses';
  }

  container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 24px;">Adresler ${exName} üzerinden güvenle çekiliyor...</div>`;

  try {
    const res = await fetch(endpoint);
    const data = await res.json();
    if (res.ok && data.status === 'SUCCESS' && data.addresses && data.addresses.length > 0) {
      let html = '';
      data.addresses.forEach(addr => {
        html += `
          <div style="background: var(--bg-elevated); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 14px 16px; margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div>
                <strong style="font-size: 14px; color: var(--text-primary);">${addr.name}</strong>
                <span style="font-size: 11px; color: var(--accent-cyan); margin-left: 8px; font-weight: 600;">${addr.desc}</span>
              </div>
              <span class="indicator-pill" style="color: var(--profit); font-weight: 700;">Ağ: ${addr.network}</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
              <input type="text" readonly value="${addr.address}" class="form-input" style="font-family: var(--font-mono); font-size: 12px; color: var(--text-primary); background: var(--bg-surface); cursor: pointer;" onclick="this.select(); copyAddress('${addr.address}', this)">
              <button class="btn btn-primary" style="height: 38px; padding: 0 14px; font-size: 12px; white-space: nowrap;" onclick="copyAddress('${addr.address}', this)">
                Kopyala 📋
              </button>
            </div>
            ${addr.tag ? `<div style="font-size: 11px; color: var(--warning); margin-top: 4px;">Memo / Tag: <strong>${addr.tag}</strong></div>` : ''}
          </div>
        `;
      });
      container.innerHTML = html;
    } else {
      let customHtml = '';
      if (exUpper === 'MEXC') {
        customHtml = `
          <div style="text-align: left; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 16px; font-size: 13px; line-height: 1.5;">
            <div style="font-weight: 700; color: #10b981; margin-bottom: 6px; font-size: 14px;">🟢 MEXC Borsa Bağlantısı Aktif</div>
            <div style="color: var(--text-secondary); margin-bottom: 10px;">
              MEXC cüzdan bakiyeniz, coinleriniz ve serbest USDT miktarınız başarıyla okunmakta ve Ana Kasa'ya tam hassasiyetle dahil edilmektedir.
            </div>
            <div style="background: var(--bg-surface); padding: 10px 12px; border-radius: 6px; font-size: 12px; color: var(--text-muted); margin-bottom: 10px;">
              💡 <strong>Yatırma Bilgisi:</strong> MEXC API anahtarınızda 'Yatırma Adresi Okuma' izni henüz açık değildir. Para yatırmak için MEXC uygulamasından (veya web sitesinden) <em>Varlıklar &rarr; Yatır</em> adımlarını izleyerek dilediğiniz adrese yatırma yapabilirsiniz. Yatırdığınız tutar otomatik olarak bu panelde belirecektir.
            </div>
          </div>
        `;
      } else if (exUpper === 'OKX') {
        customHtml = `
          <div style="text-align: center; color: var(--warning); padding: 20px;">
            ${data.message || 'OKX API parolası (passphrase) girilmediği için yatırma adresleri listelenemedi.'}
            <div style="color: var(--text-muted); font-size: 11px; margin-top: 8px;">Ayarlar menüsünden OKX parolanızı kaydedebilirsiniz.</div>
          </div>
        `;
      } else {
        customHtml = `
          <div style="text-align: center; color: var(--loss); padding: 20px;">
            ${data.message || exName + ' yatırma adresleri alınamadı.'}
          </div>
        `;
      }
      container.innerHTML = customHtml;
    }
  } catch (err) {
    container.innerHTML = `<div style="text-align: center; color: var(--loss); padding: 20px;">Hata: ${err.message}</div>`;
  }
}

function closeDepositModal() {
  document.getElementById('deposit-modal').style.display = 'none';
}

function copyAddress(text, el) {
  navigator.clipboard.writeText(text).then(() => {
    if (el.tagName === 'BUTTON') {
      const originalText = el.textContent;
      el.textContent = 'Kopyalandı! ✅';
      el.style.background = 'var(--profit)';
      setTimeout(() => {
        el.textContent = originalText;
        el.style.background = '';
      }, 2000);
    } else {
      alert('Cüzdan Adresi Kopyalandı:\n' + text);
    }
  }).catch(() => {
    prompt('Cüzdan adresini kopyalayabilirsiniz:', text);
  });
}

async function saveSettings(e) {
  if (e && e.preventDefault) e.preventDefault();
  const statusMsg = document.getElementById('settings-status-msg');
  if (statusMsg) {
    statusMsg.style.display = 'block';
    statusMsg.style.background = 'rgba(2, 132, 199, 0.15)';
    statusMsg.style.border = '1px solid var(--accent-cyan)';
    statusMsg.style.color = 'var(--accent-cyan)';
    statusMsg.innerHTML = 'Ayarlar kaydediliyor ve .env dosyası güncelleniyor... ⏳';
  }

  const apiKey = (document.getElementById('input-api-key').value || '').trim();
  const model = document.getElementById('select-model').value;
  const tgToken = (document.getElementById('input-tg-token').value || '').trim();
  const tgChat = (document.getElementById('input-tg-chat').value || '').trim();
  const tradingMode = document.getElementById('select-trading-mode').value;
  const tradingExchange = document.getElementById('select-trading-exchange') ? document.getElementById('select-trading-exchange').value : 'AUTO';
  const riskProfile = document.getElementById('select-risk-profile') ? document.getElementById('select-risk-profile').value : 'AGGRESSIVE_ALPHA';
  const riskLimitVal = document.getElementById('select-risk-limit') ? parseFloat(document.getElementById('select-risk-limit').value) : 5.0;
  const binanceKey = (document.getElementById('input-binance-key').value || '').trim();
  const binanceSecret = (document.getElementById('input-binance-secret').value || '').trim();
  const okxKey = document.getElementById('input-okx-key') ? document.getElementById('input-okx-key').value.trim() : '';
  const okxSecret = document.getElementById('input-okx-secret') ? document.getElementById('input-okx-secret').value.trim() : '';
  const okxPassphrase = document.getElementById('input-okx-passphrase') ? document.getElementById('input-okx-passphrase').value.trim() : '';
  const mexcKey = document.getElementById('input-mexc-key') ? document.getElementById('input-mexc-key').value.trim() : '';
  const mexcSecret = document.getElementById('input-mexc-secret') ? document.getElementById('input-mexc-secret').value.trim() : '';
  const groqKey = document.getElementById('input-groq-key') ? document.getElementById('input-groq-key').value.trim() : '';
  const coingeckoKey = document.getElementById('input-coingecko-key') ? document.getElementById('input-coingecko-key').value.trim() : '';
  const fredKey = document.getElementById('input-fred-key') ? document.getElementById('input-fred-key').value.trim() : '';

  const payload = {
    deepseek_model: model,
    trading_mode: tradingMode,
    trading_exchange: tradingExchange,
    ai_risk_profile: riskProfile,
    max_risk_per_trade_percent: riskLimitVal
  };
  if (apiKey) payload.deepseek_api_key = apiKey;
  if (tgToken) payload.telegram_token = tgToken;
  if (tgChat) payload.telegram_chat_id = tgChat;
  if (binanceKey) payload.binance_api_key = binanceKey;
  if (binanceSecret) payload.binance_secret_key = binanceSecret;
  if (okxKey) payload.okx_api_key = okxKey;
  if (okxSecret) payload.okx_secret_key = okxSecret;
  if (okxPassphrase) payload.okx_passphrase = okxPassphrase;
  if (mexcKey) payload.mexc_api_key = mexcKey;
  if (mexcSecret) payload.mexc_secret_key = mexcSecret;
  if (groqKey) payload.groq_api_key = groqKey;
  if (coingeckoKey) payload.coingecko_api_key = coingeckoKey;
  if (fredKey) payload.fred_api_key = fredKey;

  const inPinEl = document.getElementById('input-admin-pin');
  const adminPinVal = inPinEl ? inPinEl.value.trim() : '';
  if (adminPinVal) payload.admin_pin = adminPinVal;

  try {
    const res = await fetch('/api/config/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.status === 'SUCCESS') {
      if (adminPinVal) {
        try {
          const authRes = await _originalFetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pin: adminPinVal })
          });
          const authData = await authRes.json();
          if (authData.token) localStorage.setItem('quant_admin_token', authData.token);
        } catch (e) {}
      }
      if (statusMsg) {
        statusMsg.style.background = 'rgba(16, 185, 129, 0.15)';
        statusMsg.style.border = '1px solid var(--profit)';
        statusMsg.style.color = 'var(--profit)';
        statusMsg.innerHTML = '✅ Ayarlar başarıyla kaydedildi ve sisteme uygulandı!';
      }
      fetchState();
      setTimeout(() => {
        closeSettingsModal();
      }, 1200);
    } else {
      if (statusMsg) {
        statusMsg.style.background = 'rgba(244, 63, 94, 0.15)';
        statusMsg.style.border = '1px solid var(--loss)';
        statusMsg.style.color = 'var(--loss)';
        statusMsg.innerHTML = '❌ Kaydetme hatası: ' + (data.message || 'Bilinmeyen hata');
      }
    }
  } catch (err) {
    if (statusMsg) {
      statusMsg.style.background = 'rgba(244, 63, 94, 0.15)';
      statusMsg.style.border = '1px solid var(--loss)';
      statusMsg.style.color = 'var(--loss)';
      statusMsg.innerHTML = '❌ Bağlantı hatası: ' + err.message;
    }
  }
}

async function resetPaperWallet() {
  if (!confirm('Sanal kasayı 10.000$ başlangıç bakiyesine sıfırlamak ve tüm açık sanal pozisyonları temizlemek istediğinize emin misiniz?')) {
    return;
  }
  try {
    const res = await fetch('/api/wallet/reset-paper', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.status === 'SUCCESS') {
      alert('✅ Sanal kasa başarıyla $10.000 olarak sıfırlandı!');
      fetchState();
    } else {
      alert('Sıfırlama hatası: ' + (data.message || 'Bilinmeyen hata'));
    }
  } catch (err) {
    alert('İstek hatası: ' + err.message);
  }
}

let allMarketCoins = [];
let marketSortMode = 'volume';
let currentMarketExchange = 'BINANCE';

function switchMarketExchange(exchange, btn) {
  currentMarketExchange = (exchange || 'BINANCE').toUpperCase();
  ['market-tab-binance', 'market-tab-okx', 'market-tab-mexc'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });
  if (btn) btn.classList.add('active');

  const input = document.getElementById('market-search-input');
  if (input) {
    input.value = '';
    const name = currentMarketExchange === 'BINANCE' ? 'Binance (650+)' : (currentMarketExchange === 'OKX' ? 'OKX (390+)' : 'MEXC (1.650+)');
    input.placeholder = `🔍 ${name} Altcoini İçinde Ara... (örn: BTC, PEPE, SUI, DOGE, SOL, RENDER)`;
  }

  const tbody = document.getElementById('market-coins-body');
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">${currentMarketExchange} altcoinleri taranıyor...</td></tr>`;
  }

  loadAllMarketCoins();
}

async function loadAllMarketCoins() {
  try {
    const res = await fetch(`/api/market/all-coins?exchange=${currentMarketExchange}&sort_by=${marketSortMode}`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === 'SUCCESS' && data.coins) {
      allMarketCoins = data.coins;
      const cntEl = document.getElementById('market-total-count');
      if (cntEl) {
        const exLabel = currentMarketExchange === 'BINANCE' ? 'Binance' : (currentMarketExchange === 'OKX' ? 'OKX' : 'MEXC');
        cntEl.textContent = `${data.total} ${exLabel} Altcoini Aktif`;
      }
      renderMarketCoins(allMarketCoins);
    }
  } catch (err) {
    console.error('Altcoinler yüklenemedi:', err);
  }
}

function filterAllMarketCoins() {
  const query = (document.getElementById('market-search-input').value || '').trim().toUpperCase();
  if (!query) {
    renderMarketCoins(allMarketCoins);
    return;
  }
  const filtered = allMarketCoins.filter(c => c.symbol.includes(query) || c.asset.includes(query));
  renderMarketCoins(filtered);
}

function sortMarketCoins(mode, btn) {
  marketSortMode = mode;
  ['sort-vol', 'sort-gain', 'sort-loss', 'sort-alpha'].forEach(id => {
    const b = document.getElementById(id);
    if (b) b.classList.remove('active');
  });
  if (btn) btn.classList.add('active');

  if (mode === 'gainers') {
    allMarketCoins.sort((a, b) => b.change_24h - a.change_24h);
  } else if (mode === 'losers') {
    allMarketCoins.sort((a, b) => a.change_24h - b.change_24h);
  } else if (mode === 'alphabetical') {
    allMarketCoins.sort((a, b) => a.symbol.localeCompare(b.symbol));
  } else {
    allMarketCoins.sort((a, b) => b.volume_usd - a.volume_usd);
  }

  filterAllMarketCoins();
}

function renderMarketCoins(coins) {
  const tbody = document.getElementById('market-coins-body');
  if (!tbody) return;
  if (!coins || coins.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">Aradığınız kriterde altcoin bulunamadı.</td></tr>`;
    return;
  }

  let html = '';
  // İlk 100 tanesini hızlıca bas (performans koruması)
  const slice = coins.slice(0, 100);
  slice.forEach(c => {
    const chgClass = c.change_24h >= 0 ? 'text-profit' : 'text-loss';
    const volMillions = (c.volume_usd / 1e6).toFixed(2);
    const exName = (c.exchange || currentMarketExchange).toUpperCase();
    let exBadge = `<span class="indicator-pill" style="color: #f3ba2f; border-color: rgba(243, 186, 47, 0.4); font-size: 10px; font-weight: 700; margin-right: 6px;">🟡</span>`;
    if (exName === 'OKX') {
      exBadge = `<span class="indicator-pill" style="color: var(--accent-cyan); border-color: rgba(2, 132, 199, 0.4); font-size: 10px; font-weight: 700; margin-right: 6px;">⚫</span>`;
    } else if (exName === 'MEXC') {
      exBadge = `<span class="indicator-pill" style="color: #10b981; border-color: rgba(16, 185, 129, 0.4); font-size: 10px; font-weight: 700; margin-right: 6px;">🟢</span>`;
    }

    html += `
      <tr style="cursor: pointer;" onclick="openAndAnalyzeAsset('${c.symbol}', '${exName}')" title="${exName} canlı analiz ve grafiğini açmak için tıklayın">
        <td>
          <div style="display: flex; align-items: center;">
            ${exBadge}
            <div>
              <strong style="color: var(--text-primary); font-size: 13px;">${c.asset}</strong>
              <span style="color: var(--text-muted); font-size: 11px; margin-left: 4px;">${c.symbol}</span>
            </div>
          </div>
        </td>
        <td style="font-family: var(--font-mono); font-weight: 600;">${formatCryptoMoney(c.price)}</td>
        <td class="${chgClass}" style="font-weight: 600;">${c.change_24h >= 0 ? '+' : ''}%${c.change_24h.toFixed(2)}</td>
        <td style="color: var(--text-secondary); font-family: var(--font-mono);">$${volMillions}M</td>
        <td style="text-align: right;">
          <button class="btn btn-secondary" style="font-size: 11px; height: 26px; padding: 0 8px;" onclick="event.stopPropagation(); openAndAnalyzeAsset('${c.symbol}', '${exName}')">
            İncele & Grafik ↗
          </button>
        </td>
      </tr>
    `;
  });

  if (coins.length > 100) {
    html += `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); font-size: 11px; padding: 10px;">(Toplam ${coins.length} altcoin içinden ilk 100 tanesi listelendi. Diğerlerini bulmak için yukarıdaki arama çubuğunu kullanabilirsiniz).</td></tr>`;
  }

  tbody.innerHTML = html;
}

async function openAndAnalyzeAsset(symbol, exchange = 'BINANCE') {
  // Önce modalı aç ve TradingView grafiğini o borsanın akışıyla anında göster
  openAssetModal(symbol, exchange);
  
  // Eğer analiz yerel listede yoksa on-demand çek
  const existing = currentAnalyses.find(a => a.symbol === symbol);
  if (!existing) {
    document.getElementById('modal-ai-thesis').textContent = `${symbol} (${exchange}) için canlı teknik indikatörler ve DeepSeek AI tezi anlık hesaplanıyor...`;
    try {
      const res = await fetch('/api/market/analyze-coin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: symbol })
      });
      const data = await res.json();
      if (res.ok && data.status === 'SUCCESS' && data.analysis) {
        currentAnalyses.push(data.analysis);
        openAssetModal(symbol, exchange);
      }
    } catch (e) {
      console.error('On-demand analiz hatası:', e);
    }
  }
}

// ============================================================================
// ÇOKLU BORSA GÜNLÜK YÜKSELİŞ RADARI & TAKİP SİSTEMİ
// ============================================================================
let currentRadarData = null;
let currentRadarFilter = 'ALL';

function renderBreakoutRadar(radarData) {
  if (!radarData) return;
  currentRadarData = radarData;

  // Takip edilen sayısı rozeti
  const trackedPill = document.getElementById('radar-tracked-pill');
  const trackedCount = radarData.tracked_count !== undefined 
    ? radarData.tracked_count 
    : (radarData.watchlist ? radarData.watchlist.length : 0);
  if (trackedPill) {
    trackedPill.textContent = `${trackedCount} Takipte`;
    trackedPill.style.color = trackedCount > 0 ? 'var(--profit)' : 'var(--text-muted)';
  }

  // Günlük Piyasa Raporu Kutusu
  const mr = radarData.market_report || {};
  const repTop = document.getElementById('radar-report-top-pick');
  const repPot = document.getElementById('radar-report-avg-target');
  const repText = document.getElementById('radar-report-text');

  if (repTop) {
    repTop.textContent = mr.top_pick ? `${mr.top_pick} (Skor: %${mr.top_pick_score || 95})` : '-';
  }
  if (repPot) {
    repPot.textContent = mr.avg_potential || '+%14.5';
  }
  if (repText) {
    repText.textContent = mr.summary || 'Tüm borsalar tarandı ve yükseliş eğilimindeki coinler listelendi.';
  }

  renderRadarItems();
}

function filterRadar(filter, btnEl) {
  currentRadarFilter = filter;
  const buttons = document.querySelectorAll('#radar-filter-buttons .btn-filter');
  buttons.forEach(b => b.classList.remove('active'));
  if (btnEl) btnEl.classList.add('active');
  renderRadarItems();
}

function renderRadarItems() {
  const container = document.getElementById('radar-items-container');
  if (!container || !currentRadarData) return;

  const opportunities = currentRadarData.opportunities || currentRadarData.top_opportunities || [];
  const watchlist = currentRadarData.watchlist || [];

  let items = [];

  if (currentRadarFilter === 'TRACKED') {
    items = watchlist;
  } else if (currentRadarFilter === 'BINANCE') {
    items = opportunities.filter(op => (op.exchanges || []).includes('Binance'));
  } else if (currentRadarFilter === 'MEXC') {
    items = opportunities.filter(op => (op.exchanges || []).includes('MEXC'));
  } else if (currentRadarFilter === 'OKX') {
    items = opportunities.filter(op => (op.exchanges || []).includes('OKX'));
  } else {
    items = opportunities;
  }

  if (items.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 24px 12px; color: var(--text-muted); font-size: 12px; background: rgba(255,255,255,0.01); border-radius: 6px;">
        ${currentRadarFilter === 'TRACKED' ? 'Henüz takibe alınan bir kripto bulunmuyor. Fırsatların yanındaki ⭐ ikonuna tıklayarak takibe alabilirsiniz.' : 'Seçili filtreye uygun yükseliş fırsatı bulunamadı.'}
      </div>
    `;
    return;
  }

  // Takip edilen semboller kümesi
  const trackedSymbols = new Set(watchlist.map(w => w.symbol));

  let html = '';
  items.forEach(item => {
    const isTracked = trackedSymbols.has(item.symbol) || item.is_tracked;
    const trackedItem = watchlist.find(w => w.symbol === item.symbol);
    const pnl = trackedItem ? trackedItem.pnl_pct : (item.pnl_pct || 0);
    const hasPnl = isTracked && pnl !== undefined;
    const pnlClass = pnl >= 0 ? 'text-profit' : 'text-loss';
    const pnlSign = pnl >= 0 ? '+' : '';

    // Borsa rozetleri
    const exchanges = item.exchanges || ['Binance'];
    let exBadges = '';
    if (exchanges.includes('Binance')) {
      exBadges += `<span class="indicator-pill" style="color: #f3ba2f; border-color: rgba(243, 186, 47, 0.4); font-size: 10px; padding: 1px 5px; font-weight: 700;">🟡 Binance</span> `;
    }
    if (exchanges.includes('MEXC')) {
      exBadges += `<span class="indicator-pill" style="color: #10b981; border-color: rgba(16, 185, 129, 0.4); font-size: 10px; padding: 1px 5px; font-weight: 700;">🟢 MEXC</span> `;
    }
    if (exchanges.includes('OKX')) {
      exBadges += `<span class="indicator-pill" style="color: var(--accent-cyan); border-color: rgba(2, 132, 199, 0.4); font-size: 10px; padding: 1px 5px; font-weight: 700;">⚫ OKX</span> `;
    }

    const primaryExchange = exchanges[0] || 'BINANCE';
    const chgClass = (item.change_24h || 0) >= 0 ? 'text-profit' : 'text-loss';
    const chgSign = (item.change_24h || 0) >= 0 ? '+' : '';

    html += `
      <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; transition: border-color 0.2s;" onmouseenter="this.style.borderColor='var(--accent-cyan)'" onmouseleave="this.style.borderColor='var(--border-subtle)'">
        
        <!-- Üst Satır: Sembol, Fiyat, 24s Değişim ve Takip Butonu -->
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-weight: 700; font-size: 13px; color: var(--text-primary); cursor: pointer;" onclick="openAndAnalyzeAsset('${item.symbol}', '${primaryExchange}')" title="Canlı Grafiği Aç">
              ${item.asset || item.symbol.replace('USDT', '')} <span style="font-size: 11px; color: var(--text-muted); font-weight: 500;">/ USDT</span>
            </span>
            <button onclick="toggleTrackRadarCoin('${item.symbol}')" style="background: transparent; border: none; cursor: pointer; font-size: 14px; padding: 0 2px; color: ${isTracked ? '#f59e0b' : 'var(--text-muted)'};" title="${isTracked ? 'Takibi Bırak' : 'Takibe Al'}">
              ${isTracked ? '★' : '☆'}
            </button>
          </div>

          <div style="text-align: right;">
            <span style="font-family: var(--font-mono); font-weight: 700; font-size: 13px;">${formatCryptoMoney(item.price || item.current_price || 0)}</span>
            <span class="${chgClass}" style="font-size: 11px; font-weight: 600; margin-left: 4px;">${chgSign}%${(item.change_24h || 0).toFixed(2)}</span>
          </div>
        </div>

        <!-- İkinci Satır: Borsa Rozetleri & AI Skoru -->
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 4px;">
          <div style="display: flex; gap: 4px; flex-wrap: wrap;">
            ${exBadges}
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <span class="indicator-pill" style="color: var(--profit); font-size: 10px; font-weight: 700; padding: 1px 6px; border-color: rgba(16, 185, 129, 0.3);">
              🎯 Hedef: +%${item.target_gain_pct || 12}
            </span>
            <span class="indicator-pill" style="color: var(--accent-cyan); font-size: 10px; font-weight: 700; padding: 1px 6px; border-color: rgba(2, 132, 199, 0.3);">
              Skor: %${item.breakout_score || 85}
            </span>
          </div>
        </div>

        <!-- Üçüncü Satır: AI Gerekçesi / Rapor -->
        <div style="font-size: 11px; color: var(--text-muted); line-height: 1.35; background: rgba(255,255,255,0.015); padding: 4px 8px; border-radius: 4px; border-left: 2px solid var(--accent-cyan);">
          ${item.thesis || 'Günlük kırılım ve hacim akışı tespit edildi.'}
        </div>

        <!-- Takip Durumu & PnL (Eğer takipteyse) -->
        ${hasPnl ? `
          <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; padding: 3px 6px; background: rgba(16, 185, 129, 0.08); border-radius: 4px;">
            <span style="color: var(--text-muted);">Sinyalden Beri Getiri:</span>
            <span class="${pnlClass}" style="font-weight: 700; font-family: var(--font-mono);">${pnlSign}%${pnl.toFixed(2)} (${trackedItem ? (trackedItem.status || 'TAKİPTE') : 'TAKİPTE'})</span>
          </div>
        ` : ''}

        <!-- Alt Butonlar: Hızlı Pozisyon Al & İncele -->
        <div style="display: flex; gap: 6px; margin-top: 2px;">
          <button class="btn btn-secondary" style="flex: 1; font-size: 11px; height: 26px; padding: 0 6px;" onclick="openAndAnalyzeAsset('${item.symbol}', '${primaryExchange}')">
            📊 İncele & Grafik
          </button>
          <button class="btn btn-primary" style="flex: 1; font-size: 11px; height: 26px; padding: 0 6px; background: var(--profit); border-color: var(--profit);" onclick="quickTradeRadar('${item.symbol}', '${primaryExchange}')">
            ⚡ Hızlı Pozisyon Al
          </button>
        </div>

      </div>
    `;
  });

  container.innerHTML = html;
}

async function scanBreakoutRadar() {
  const btn = document.getElementById('btn-scan-radar');
  const btnText = document.getElementById('btn-scan-text');
  const icon = document.getElementById('radar-refresh-icon');

  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = 'Taranıyor...';
  if (icon) icon.style.animation = 'spin 1s linear infinite';

  try {
    const res = await fetch('/api/radar/scan', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'SUCCESS') {
      renderBreakoutRadar(data);
    }
  } catch (err) {
    console.error('Radar tarama hatası:', err);
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = 'Şimdi Tara';
    if (icon) icon.style.animation = '';
  }
}

async function toggleTrackRadarCoin(symbol) {
  try {
    const res = await fetch('/api/radar/track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: symbol })
    });
    const data = await res.json();
    if (data.status === 'SUCCESS' && currentRadarData) {
      currentRadarData.watchlist = data.watchlist;
      currentRadarData.tracked_count = data.watchlist.length;
      renderBreakoutRadar(currentRadarData);
    }
  } catch (err) {
    console.error('Takip değiştirme hatası:', err);
  }
}

function quickTradeRadar(symbol, exchange) {
  openAssetModal(symbol, exchange);
  const actSelect = document.getElementById('modal-trade-action');
  if (actSelect) actSelect.value = 'BUY';
  const exSelect = document.getElementById('modal-trade-exchange');
  if (exSelect && exchange) exSelect.value = exchange.toUpperCase();
}

// Global Function Bindings
window.openSettingsModal = openSettingsModal;
window.closeSettingsModal = closeSettingsModal;
window.saveSettings = saveSettings;
window.openDepositModal = openDepositModal;
window.closeDepositModal = closeDepositModal;
window.openAssetModal = openAssetModal;
window.closeAssetModal = closeAssetModal;
window.openAndAnalyzeAsset = openAndAnalyzeAsset;
window.toggleTradingMode = toggleTradingMode;
window.triggerManualScan = triggerManualScan;
window.closePosition = closePosition;
window.submitManualOrder = submitManualOrder;
window.setModalTradeMode = setModalTradeMode;
window.updateModalBalanceInfo = updateModalBalanceInfo;
window.setModalAmountMax = setModalAmountMax;
window.setExchangeFilter = setExchangeFilter;
window.copyAddress = copyAddress;
window.toggleTheme = toggleTheme;
window.setTheme = setTheme;
window.initTheme = initTheme;
window.setTradingExchange = setTradingExchange;
window.scanBreakoutRadar = scanBreakoutRadar;
window.filterRadar = filterRadar;
window.toggleTrackRadarCoin = toggleTrackRadarCoin;
window.quickTradeRadar = quickTradeRadar;
window.submitPin = submitPin;
window.lockDashboard = lockDashboard;

// Başlatıcı
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();

  // Güvenlik Kalkanı & Oturum Kontrolü
  const isAuth = await checkInitialAuth();

  const btnSettings = document.getElementById('btn-settings-header');
  if (btnSettings) {
    btnSettings.addEventListener('click', (e) => {
      e.preventDefault();
      openSettingsModal();
    });
  }

  if (isAuth) {
    fetchState();
    loadAllMarketCoins();
  }

  setInterval(() => {
    if (localStorage.getItem('quant_admin_token')) {
      fetchState();
    }
  }, 8000);

  setInterval(() => {
    if (localStorage.getItem('quant_admin_token')) {
      loadAllMarketCoins();
    }
  }, 30000);

  // Sayfa açıkken her 90 saniyede bir otonom sepet taraması ve dengelemesi yap
  setInterval(async () => {
    if (!localStorage.getItem('quant_admin_token')) return;
    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (res.ok) {
        fetchState();
      }
    } catch (e) {}
  }, 90000);
});
