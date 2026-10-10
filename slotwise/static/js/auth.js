const form = document.querySelector("form");
const message = document.querySelector("#auth-message");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Working...";
  message.textContent = "";
  const isRegister = form.id === "register-form";
  try {
    const response = await fetch(isRegister ? "/api/auth/register" : "/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(new FormData(form).entries())),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Unable to continue.");
    window.location.assign("/");
  } catch (error) {
    message.textContent = error.message;
    button.disabled = false;
    button.textContent = isRegister ? "Create account" : "Sign in";
  }
});
