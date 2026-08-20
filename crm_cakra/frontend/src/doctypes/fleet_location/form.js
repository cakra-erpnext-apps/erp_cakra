// Fleet Location yang dibuat dari CRM selalu untuk keperluan rute (Origin/Destination
// di Inquiry), jadi "Route" dikunci tercentang. Nilai centangnya diisi saat modal
// dibuka (lihat field.create di FieldLayout/Field.vue); di sini hanya dikunci.
export class FleetLocation {
  onLoad() {
    this.setFieldProperty('is_route', 'read_only', 1)
  }
}
