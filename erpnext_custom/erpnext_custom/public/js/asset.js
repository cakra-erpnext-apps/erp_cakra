// Aset di kategori "Kendaraan (Fleet)" dipasangkan 1:1 dengan record Vehicle.
// Vehicle-nya TIDAK dibuat otomatis (nopol/branch/varian harus diisi user), jadi form aset
// dapat blok "Vehicle" di sidebar (di bawah Share): belum ada pasangan -> tautan
// "Create Vehicle"; sudah ada -> nopolnya, sebagai tautan ke form Vehicle.
frappe.ui.form.on("Asset", {
	refresh(frm) {
		frm.sidebar?.sidebar?.find(".asset-vehicle-section").remove();
		if (frm.is_new()) return;
		if (frm.doc.custom_vehicle) return render_vehicle_section(frm);
		frappe.db.get_value("Asset Category", frm.doc.asset_category, "custom_is_vehicle").then((r) => {
			if (r.message?.custom_is_vehicle) render_vehicle_section(frm);
		});
	},
});

function render_vehicle_section(frm) {
	const shared = frm.sidebar?.sidebar?.find(".form-shared");
	if (!shared?.length) return;
	shared.next(".asset-vehicle-section").remove();

	const body = frm.doc.custom_vehicle
		? $("<a class='ellipsis'></a>")
				.text(frm.doc.custom_vehicle)
				.attr("href", frappe.utils.get_form_link("Vehicle", frm.doc.custom_vehicle))
		: $("<a class='badge-hover'></a>").text(__("Create Vehicle")).on("click", () => new_vehicle(frm));

	$(`<div class="sidebar-section asset-vehicle-section border-bottom">
			<div class="sidebar-label">${__("Vehicle")}</div>
			<div class="asset-vehicle-body"></div>
		</div>`)
		.insertAfter(shared)
		.find(".asset-vehicle-body")
		.append(body);
}

// Branch Vehicle diturunkan dari Location asetnya. Belum ada field pemetaan Location ->
// CMI Office, jadi dicocokkan lewat Location.title (mis. Location "JKT" -> title "Jakarta"
// -> CMI Office "Jakarta"); kalau tidak ketemu, branch dibiarkan kosong untuk diisi user.
// ponytail: cocok-nama, ganti ke field pemetaan kalau nama kantor mulai berbeda.
function new_vehicle(frm) {
	const open = (branch) =>
		frappe.new_doc("Vehicle", {
			asset: frm.doc.name,
			branch: branch || undefined,
			merk: frm.doc.item_name || frm.doc.asset_name,
			tahun_pembuatan: frm.doc.purchase_date
				? frappe.datetime.str_to_obj(frm.doc.purchase_date).getFullYear()
				: undefined,
		});

	if (!frm.doc.location) return open();
	frappe.db.get_value("Location", frm.doc.location, "title").then((r) => {
		const office = r.message?.title;
		if (!office) return open();
		frappe.db.exists("CMI Office", office).then((ada) => open(ada ? office : null));
	});
}
