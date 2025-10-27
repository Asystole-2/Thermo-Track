(function () {
  // Step 1 — Recognizer factory and engines
  function WebSpeechRecognizer(lang = 'en-IE') {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) throw new Error('Web Speech API not supported');

    const r = new SR();
    r.lang = lang;
    r.interimResults = false;
    r.maxAlternatives = 1;

    return {
      start(onText, onState) {
        r.onstart = () => onState?.('listening');
        r.onend   = () => onState?.('idle');
        r.onerror = e => onState?.('error:' + e.error);
        r.onresult = e => {
          const text = e.results[0][0].transcript.trim();
          onText(text);
        };
        r.start();
      }
    };
  }

  // Step 2 — Create recognizer (pluggable)
  function createRecognizer() {
    try {
      return WebSpeechRecognizer('en-IE');
    } catch (err) {
      console.warn('Voice engine unavailable:', err.message);
      return null;
    }
  }

  // Step 3 — Apply to voiceable fields
  const asr = createRecognizer();
  if (!asr) return;

  window.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tt_voiceable').forEach(input => {
      const type = (input.type || '').toLowerCase();
      if (type === 'password') return;

      // Create wrapper and elements
      const wrap = document.createElement('div');
      wrap.className = 'voice-input-wrapper';
      input.parentNode.insertBefore(wrap, input);
      wrap.appendChild(input);

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = '🎤';
      btn.className = 'tt_micButton';
      wrap.appendChild(btn);

      const status = document.createElement('span');
      status.className = 'voice-status';
      wrap.appendChild(status);

      const mode = (input.dataset.voiceMode || 'replace').toLowerCase();

      btn.addEventListener('click', () => {
        if (!asr) return;
        input.focus();
        asr.start(
          text => {
            if (mode === 'append' && input.value) {
              input.value = input.value.replace(/\s*$/, '') + ' ' + text;
            } else {
              input.value = text;
            }
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            status.textContent = 'Heard: ' + text;
            setTimeout(() => (status.textContent = ''), 2500);
          },
          state => {
            if (state === 'listening') status.textContent = 'Listening…';
            else if (state.startsWith('error')) status.textContent = 'Mic error';
            else status.textContent = '';
          }
        );
      });
    });
  });
})();