// Menu Tax Invoice / Tax Expense / Tax ARAP Note / Tax Purchase: satu halaman, dibedakan ?type=.
// Daftar dokumen berpajak; klik baris -> modal isi Tax No. Datanya di doctype Tax Number
// (tax_number.py): Execution = pengisi pertama, Modify = pengubah terakhir.
const TAX_TITLES = {
	invoice: "Tax Invoice",
	expense: "Tax Expense",
	arap: "Tax ARAP Note",
	purchase: "Tax Purchase",
};
const TAX_API = "erpnext_custom.erpnext_custom.doctype.tax_number.tax_number.";

frappe.pages["tax-register"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Tax"), single_column: true });
	const state = { type: null, rows: [] };

	const field = (df) => page.add_field({ ...df, change: () => load() });
	const from = field({ fieldname: "from_date", label: __("From"), fieldtype: "Date",
		default: frappe.datetime.add_months(frappe.datetime.month_start(), -1) });
	const to = field({ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() });
	const status = field({ fieldname: "status", label: __("Status"), fieldtype: "Select",
		options: ["", "Belum", "Sudah"].join("\n") });
	const search = field({ fieldname: "search", label: __("Search"), fieldtype: "Data" });
	page.set_primary_action(__("Refresh"), () => load(), "refresh");

	// Kerangka & kelas CSS list view bawaan (list_view.js), supaya tampil sama dengan list
	// Sales Invoice; datanya saja yang dari get_rows, dan klik baris membuka modal, bukan form.
	page.main.addClass("layout-main-list");
	page.page_form.removeClass("row").addClass("flex");
	const $list = $(`<div class="frappe-list">
		<div class="result-container"><div class="result"></div></div>
		<div class="no-result text-muted flex justify-center align-center">${__("Nothing to show")}</div>
	</div>`).appendTo(page.main);
	const $result = $list.find(".result");
	const $empty = $list.find(".no-result");
	const esc = frappe.utils.escape_html;
	// buang mikrodetik: "2026-09-28 15:26:01.200574" ditolak parser tanggal frappe
	const dt = (v) => (v ? frappe.datetime.str_to_user(String(v).split(".")[0]) : "");
	const col = (cls, html) => `<div class="list-row-col ellipsis ${cls}">${html}</div>`;
	const pill = (r) => `<span class="indicator-pill ${r.tax_no ? "green" : "orange"} ellipsis">
		<span class="ellipsis">${r.tax_no ? __("Sudah") : __("Belum")}</span></span>`;

	function load() {
		if (!state.type || !from.get_value() || !to.get_value()) return;
		frappe.call({
			method: TAX_API + "get_rows",
			args: { type: state.type, from_date: from.get_value(), to_date: to.get_value(),
				status: status.get_value(), search: search.get_value() },
			callback: (r) => render((state.rows = r.message || [])),
		});
	}

	function render(rows) {
		const head = [
			col("list-subject level", `<span class="level-item">${__("No Transaksi")}</span>`),
			col("hidden-xs", __("Status")),
			col("hidden-xs", __("Customer / Supplier")),
			col("hidden-xs", __("Date")),
			col("hidden-xs text-right", __("PPN")),
			col("hidden-xs text-right", __("PPh")),
			col("hidden-xs", __("Tax No")),
		].join("");
		const body = rows.map((r, i) => `
			<div class="list-row-container" tabindex="1" data-i="${i}">
				<div class="level list-row">
					<div class="level-left ellipsis">
						${col("list-subject level", `<span class="level-item bold ellipsis" title="${esc(r.name)}">${esc(r.name)}</span>`)}
						${col("hidden-xs", pill(r))}
						${col("hidden-xs", esc(r.party || ""))}
						${col("hidden-xs", dt(r.date))}
						${col("hidden-xs text-right", format_currency(r.ppn))}
						${col("hidden-xs text-right", format_currency(r.pph))}
						${col("hidden-xs", esc(r.tax_no || ""))}
					</div>
					<div class="level-right text-muted ellipsis">
						<span class="level-item list-row-activity hidden-xs"
							title="${r.modify_by ? esc(frappe.user.full_name(r.modify_by)) + " " + dt(r.modify_date) : ""}">
							${r.modify_date ? frappe.datetime.comment_when(String(r.modify_date).split(".")[0], true) : ""}
						</span>
					</div>
				</div>
			</div>`).join("");
		$result.html(`
			<div class="list-row-container">
				<header class="level list-row-head text-muted">
					<div class="level-left list-header-subject">${head}</div>
					<div class="level-right"><span class="list-count">${__("{0} of {1}", [rows.length, rows.length])}</span></div>
				</header>
			</div>${body}`);
		$empty.toggle(!rows.length);
	}

	$result.on("click", ".list-row-container[data-i]", function () {
		open_dialog(state.rows[$(this).data("i")]);
	});

	function open_dialog(r) {
		const ro = (fieldname, label, fieldtype, value) => ({ fieldname, label, fieldtype, default: value, read_only: 1 });
		const d = new frappe.ui.Dialog({
			title: __("Tax No"),
			size: "large",
			fields: [
				ro("name", __("No Transaksi"), "Data", r.name),
				{ fieldtype: "Column Break" },
				ro("party", __("Customer / Supplier"), "Data", r.party),
				{ fieldtype: "Column Break" },
				ro("date", __("Date"), "Data", dt(r.date)),
				{ fieldtype: "Section Break" },
				{ fieldname: "tax_no", label: __("No Tax"), fieldtype: "Data", default: r.tax_no },
				{ fieldtype: "Section Break", label: __("Execution") },
				ro("execution_date", __("Execution Date"), "Data", dt(r.execution_date)),
				{ fieldtype: "Column Break" },
				ro("execution_by", __("Execution By"), "Data", r.execution_by && frappe.user.full_name(r.execution_by)),
				{ fieldtype: "Column Break" },
				ro("modify_date", __("Modify Date"), "Data", dt(r.modify_date)),
				{ fieldtype: "Column Break" },
				ro("modify_by", __("Modify By"), "Data", r.modify_by && frappe.user.full_name(r.modify_by)),
			],
			primary_action_label: __("Save"),
			primary_action: (v) => {
				frappe.call({
					method: TAX_API + "save",
					args: { doctype: r.doctype, name: r.name, tax_no: v.tax_no || "" },
					freeze: true,
					callback: () => {
						d.hide();
						frappe.show_alert({ message: __("Tax No tersimpan"), indicator: "green" });
						load();
					},
				});
			},
		});
		d.show();
	}

	// Keempat menu membuka halaman yang sama; show terpanggil tiap menu diklik.
	wrapper.tax_show = () => {
		const type = (frappe.route_options && frappe.route_options.type) || frappe.utils.get_url_arg("type") || "invoice";
		if (frappe.route_options) delete frappe.route_options.type;
		if (!TAX_TITLES[type]) return;
		if (type !== state.type) {
			state.type = type;
			page.set_title(__(TAX_TITLES[type]));
			$result.empty();
		}
		load();
	};
};

frappe.pages["tax-register"].on_page_show = function (wrapper) {
	wrapper.tax_show();
};
