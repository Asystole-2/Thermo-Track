document.addEventListener("DOMContentLoaded", () => {
  const f = document.getElementById("registerForm");

  const username = document.getElementById("username");
  const email    = document.getElementById("email");
  const password = document.getElementById("password");
  const confirm  = document.getElementById("confirmation");

  const eUser = document.getElementById("usernameError");
  const eMail = document.getElementById("emailError");
  const ePass = document.getElementById("passwordError");
  const eConf = document.getElementById("confirmError");

  const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const pwdRe   = /^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+\=\[\]\{\};:'",.<>\/?\\|`~]).{8,}$/;

  function setErr(input, node, msg) {
    node.textContent = msg || "";
    if (msg) {
      node.classList.remove("hidden");
      input.classList.remove("border-gray-600", "focus:ring-blue-500");
      input.classList.add("border-red-500", "focus:ring-red-500");
    } else {
      node.classList.add("hidden");
      input.classList.remove("border-red-500", "focus:ring-red-500");
      input.classList.add("border-gray-600", "focus:ring-blue-500");
    }
  }

  function validateUsername() {
    const v = username.value.trim();
    if (!v) { setErr(username, eUser, "Username is required."); return false; }
    setErr(username, eUser, ""); return true;
  }
  function validateEmail() {
    const v = email.value.trim();
    if (!v) { setErr(email, eMail, "Email address is required."); return false; }
    if (!emailRe.test(v)) { setErr(email, eMail, "Please enter a valid email address."); return false; }
    setErr(email, eMail, ""); return true;
  }
  function validatePassword() {
    const v = password.value.trim();
    if (!v) { setErr(password, ePass, "Password is required."); return false; }
    if (!pwdRe.test(v)) { setErr(password, ePass, "Password must be ≥ 8 chars, include one uppercase, one number, and one symbol."); return false; }
    setErr(password, ePass, ""); return true;
  }
  function validateConfirm() {
    const v = confirm.value.trim();
    if (!v) { setErr(confirm, eConf, "Please confirm your password."); return false; }
    if (v !== password.value.trim()) { setErr(confirm, eConf, "Passwords do not match."); return false; }
    setErr(confirm, eConf, ""); return true;
  }

  username.addEventListener("input", validateUsername);
  email.addEventListener("input",    validateEmail);
  password.addEventListener("input", () => { validatePassword(); validateConfirm(); });
  confirm.addEventListener("input",  validateConfirm);

  f.addEventListener("submit", (e) => {
    const ok = validateUsername() & validateEmail() & validatePassword() & validateConfirm();
    if (!ok) e.preventDefault();
  });
});