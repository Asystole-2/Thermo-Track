(function () {
  // Step 1 — Recognizer factory and engines
  function WebSpeechRecognizer(lang = 'en-US') {
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
      return WebSpeechRecognizer('en-US');
    } catch (err) {
      console.warn('Voice engine unavailable:', err.message);
      return null;
    }
  }

  // Step 3 — Temperature validation and range enforcement
  function validateAndClampTemperature(value, inputElement) {
    if (isNaN(value)) {
      return { valid: false, message: 'Invalid temperature value' };
    }

    // Get temperature range from input attributes or use defaults
    const min = parseFloat(inputElement.getAttribute('min')) || 16;
    const max = parseFloat(inputElement.getAttribute('max')) || 28;

    let validatedValue = value;
    let message = '';

    if (value < min) {
      validatedValue = min;
      message = `Too low! Set to minimum ${min}°C`;
    } else if (value > max) {
      validatedValue = max;
      message = `Too high! Set to maximum ${max}°C`;
    } else {
      message = `Set to ${validatedValue}°C`;
    }

    return {
      valid: true,
      value: validatedValue,
      message: message,
      wasAdjusted: validatedValue !== value
    };
  }

  function extractTemperatureFromSpeech(transcript) {
    // Match various temperature patterns
    const patterns = [
      /(\d+(?:\.\d+)?)\s*(degrees?)?\s*(celsius|fahrenheit|kelvin|°?c|°?f|°?k)?/i,
      /(\d+(?:\.\d+)?)\s*(c|f|k)/i,
      /set.*?(\d+(?:\.\d+)?)/i,
      /temperature.*?(\d+(?:\.\d+)?)/i,
      /^(\d+(?:\.\d+)?)$/
    ];

    for (const pattern of patterns) {
      const match = transcript.match(pattern);
      if (match) {
        return parseFloat(match[1]);
      }
    }

    // Fallback: extract first number found
    const numbers = transcript.match(/\d+(?:\.\d+)?/g);
    if (numbers && numbers.length > 0) {
      return parseFloat(numbers[0]);
    }

    return null;
  }

  function updateLinkedSlider(inputElement, temperature) {
    // Find associated slider if it exists (common pattern: input_id + '_slider')
    const sliderId = inputElement.id.replace('_input', '_slider') || 'temp_setpoint_slider';
    const slider = document.getElementById(sliderId);
    if (slider && slider.type === 'range') {
      slider.value = temperature;
      slider.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  function showVoiceFeedback(message, type = 'info', duration = 3000) {
    // Remove existing feedback
    const existingFeedback = document.getElementById('tt-voice-feedback');
    if (existingFeedback) {
      existingFeedback.remove();
    }

    // Create feedback element
    const feedback = document.createElement('div');
    feedback.id = 'tt-voice-feedback';
    feedback.className = `tt-voice-feedback tt-voice-feedback-${type}`;
    feedback.textContent = message;

    // Style the feedback
    feedback.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 12px 16px;
      border-radius: 8px;
      color: white;
      font-weight: 500;
      z-index: 10000;
      max-width: 300px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      animation: tt-slideIn 0.3s ease-out;
      font-family: system-ui, -apple-system, sans-serif;
    `;

    // Style based on type
    const styles = {
      success: 'background: linear-gradient(135deg, #10b981, #059669);',
      error: 'background: linear-gradient(135deg, #ef4444, #dc2626);',
      info: 'background: linear-gradient(135deg, #3b82f6, #2563eb);',
      warning: 'background: linear-gradient(135deg, #f59e0b, #d97706);'
    };

    feedback.style.cssText += styles[type] || styles.info;

    document.body.appendChild(feedback);

    // Auto-remove after duration
    setTimeout(() => {
      if (feedback.parentNode) {
        feedback.style.animation = 'tt-slideOut 0.3s ease-in';
        setTimeout(() => feedback.remove(), 300);
      }
    }, duration);
  }

  // Step 4 — Apply to voiceable fields
  const asr = createRecognizer();
  if (!asr) return;

  // Add CSS animations and styles
  const style = document.createElement('style');
  style.textContent = `
    @keyframes tt-slideIn {
      from {
        transform: translateX(100%);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }
    
    @keyframes tt-slideOut {
      from {
        transform: translateX(0);
        opacity: 1;
      }
      to {
        transform: translateX(100%);
        opacity: 0;
      }
    }
    
    @keyframes tt-pulse {
      0% {
        box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7);
      }
      70% {
        box-shadow: 0 0 0 10px rgba(239, 68, 68, 0);
      }
      100% {
        box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
      }
    }
    
    .voice-input-wrapper {
      position: relative;
      display: inline-block;
      width: 100%;
    }
    
    .tt_micButton {
      position: absolute;
      right: 8px;
      top: 50%;
      transform: translateY(-50%);
      background: none;
      border: none;
      cursor: pointer;
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 16px;
      transition: all 0.2s ease;
      z-index: 10;
    }
    
    .tt_micButton:hover {
      background-color: rgba(59, 130, 246, 0.1);
    }
    
    .tt_micButton.listening {
      animation: tt-pulse 1.5s infinite;
      background-color: #ef4444 !important;
      color: white;
    }
    
    .voice-status {
      position: absolute;
      top: 100%;
      left: 0;
      right: 0;
      font-size: 12px;
      color: #6b7280;
      margin-top: 4px;
      min-height: 16px;
    }
    
    .tt-voice-feedback-success {
      background: linear-gradient(135deg, #10b981, #059669);
    }
    
    .tt-voice-feedback-error {
      background: linear-gradient(135deg, #ef4444, #dc2626);
    }
    
    .tt-voice-feedback-info {
      background: linear-gradient(135deg, #3b82f6, #2563eb);
    }
    
    .tt-voice-feedback-warning {
      background: linear-gradient(135deg, #f59e0b, #d97706);
    }
  `;
  document.head.appendChild(style);

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
      btn.title = 'Set temperature by voice';
      wrap.appendChild(btn);

      const status = document.createElement('span');
      status.className = 'voice-status';
      wrap.appendChild(status);

      const mode = (input.dataset.voiceMode || 'replace').toLowerCase();

      btn.addEventListener('click', () => {
        if (!asr) {
          showVoiceFeedback('Voice recognition not available', 'error');
          return;
        }

        input.focus();

        asr.start(
          text => {
            // Check if this is a temperature input
            const isTemperatureInput = input.id.includes('temp') ||
                                     input.name.includes('temp') ||
                                     input.type === 'number';

            if (isTemperatureInput) {
              const temperature = extractTemperatureFromSpeech(text);

              if (temperature === null) {
                showVoiceFeedback(`Could not understand temperature from: "${text}"`, 'error');
                status.textContent = 'No temperature found';
                return;
              }

              const validation = validateAndClampTemperature(temperature, input);

              if (!validation.valid) {
                showVoiceFeedback(validation.message, 'error');
                status.textContent = 'Invalid temperature';
                return;
              }

              // Apply the validated temperature
              input.value = validation.value;

              // Update linked slider if it exists
              updateLinkedSlider(input, validation.value);

              // Show appropriate feedback
              if (validation.wasAdjusted) {
                showVoiceFeedback(validation.message, 'warning');
                status.textContent = `Adjusted to ${validation.value}°C`;
              } else {
                showVoiceFeedback(validation.message, 'success');
                status.textContent = `Set to ${validation.value}°C`;
              }

            } else {
              // Non-temperature input handling (original behavior)
              if (mode === 'append' && input.value) {
                input.value = input.value.replace(/\s*$/, '') + ' ' + text;
              } else {
                input.value = text;
              }
              status.textContent = 'Heard: ' + text;
              showVoiceFeedback(`Text set: "${text}"`, 'success', 2000);
            }

            // Trigger events for any dependent functionality
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));

            // Clear status after delay
            setTimeout(() => {
              if (status.textContent.includes('Heard:') || status.textContent.includes('Set to')) {
                status.textContent = '';
              }
            }, 2500);
          },
          state => {
            if (state === 'listening') {
              status.textContent = 'Listening…';
              btn.classList.add('listening');
            } else if (state.startsWith('error')) {
              status.textContent = 'Mic error';
              btn.classList.remove('listening');
              showVoiceFeedback('Microphone error occurred', 'error');
            } else {
              status.textContent = '';
              btn.classList.remove('listening');
            }
          }
        );
      });
    });
  });
})();