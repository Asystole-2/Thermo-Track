document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("loginForm");
  const msgBox = document.getElementById("formMsg");

  function showMsg(text) {
    msgBox.textContent = text;
    msgBox.classList.remove("hidden");
  }

  function hideMsg() {
    msgBox.textContent = "";
    msgBox.classList.add("hidden");
  }

  form.addEventListener("submit", (e) => {
    hideMsg();
    const id = form.identifier.value.trim();
    const pwd = form.password.value.trim();

    if (!id || !pwd) {
      e.preventDefault();
      showMsg("Please enter both username/email and password.");
    }
  });
});