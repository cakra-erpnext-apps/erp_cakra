document.addEventListener("DOMContentLoaded", () => {
	const btn = document.querySelector("a.btn-login-with-email-link");
	if (!btn) return;
	if (new URLSearchParams(location.search).get("redirect-to") === "/crm/mobile") {
		btn.closest(".login-with-email-link").remove();
		return;
	}
	btn.href = "/login?redirect-to=/crm/mobile";
	btn.textContent = "Use mobile version here";
});
