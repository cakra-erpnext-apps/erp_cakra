// Smart input PPN / PPh / Discount ("11%" atau "150.000") di SEMUA form & modal: teks
// field TIDAK ditimpa selama kursor masih di field itu, baru dirapikan saat keluar.
//
// Kenapa global: Frappe memicu handler field Data lewat event `input` (debounce, lihat
// bind_change_event di frappe/form/controls/data.js), bukan hanya saat blur. Tiap form
// (Expense Note, Sales Invoice, PO/PI/SO/DN lewat cmi_amounts.js, Payment Entry, AP/AR
// Note) merapikan teksnya di handler itu -> angka yang sedang diketik berubah format di
// tengah jalan dan kursor melompat. Perhitungan & keterangan "= Rp X" di bawah field tetap
// jalan live; yang ditunda hanya penulisan ulang teks di kotak input.
(function () {
	const SMART_FIELD = /^(custom_)?(tax|pph|pph22|discount|disc)_(input|in)$/;
	const proto = frappe.ui.form.ControlData.prototype;
	if (proto.__cmi_smart_typing) return;
	proto.__cmi_smart_typing = true;
	const original = proto.set_formatted_input;

	proto.set_formatted_input = function (value) {
		if (this.$input && SMART_FIELD.test((this.df && this.df.fieldname) || "") && this.$input.is(":focus")) {
			this.__cmi_pending = value;
			if (!this.__cmi_blur_bound) {
				this.__cmi_blur_bound = true;
				this.$input.on("blur", () => setTimeout(() => {
					if (this.__cmi_pending === undefined) return;
					const v = this.__cmi_pending;
					this.__cmi_pending = undefined;
					original.call(this, v);
				}, 0));
			}
			return;
		}
		this.__cmi_pending = undefined;
		return original.call(this, value);
	};
})();
