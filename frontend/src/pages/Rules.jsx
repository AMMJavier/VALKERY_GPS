import { useState } from "react";
import { Badge, Card, ErrorBox, PageHeader, Select, Spinner } from "../components/common/ui";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { EVENT_LABELS, SEVERITY_TONE } from "../utils/status";

// Severidad por defecto (copia de valkery_core.enums.DEFAULT_SEVERITY, solo para mostrar).
const DEFAULTS = {
  IGNITION_ON: "info",
  IGNITION_OFF: "info",
  TOWING: "critical",
  CRASH: "critical",
  JAMMING: "critical",
  POWER_CUT: "critical",
  GEOFENCE_ENTER: "info",
  GEOFENCE_EXIT: "warning",
  DEVICE_ONLINE: "info",
  DEVICE_OFFLINE: "warning",
  COMMAND_SENT: "info",
  COMMAND_RESPONSE: "info",
  COMMAND_VERIFIED: "info",
  COMMAND_FAILED: "warning",
};

export function Rules() {
  const { can } = useAuth();
  const canEdit = can("event_rules:manage");
  const rules = useAsync(() => api.eventRules(), []);
  const [error, setError] = useState(null);

  const global = Object.fromEntries((rules.data ?? []).filter((r) => r.device_id == null).map((r) => [r.event_type, r]));

  async function save(type, changes) {
    setError(null);
    const current = global[type];
    try {
      await api.setEventRule({
        event_type: type,
        enabled: changes.enabled ?? current?.enabled ?? true,
        severity: "severity" in changes ? changes.severity || null : current?.severity ?? null,
      });
      rules.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageHeader title="Reglas de eventos" subtitle="Qué eventos se registran y con qué severidad (para todos los dispositivos)" />
      <Card>
        <ErrorBox error={error} />
        {rules.loading && !rules.data ? (
          <Spinner />
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="py-2">Evento</th>
                <th>Registrar</th>
                <th>Severidad</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {Object.entries(EVENT_LABELS).map(([type, label]) => {
                const rule = global[type];
                const enabled = rule?.enabled ?? true;
                const severity = rule?.severity ?? "";
                return (
                  <tr key={type}>
                    <td className="py-2">
                      <p className="font-medium">{label}</p>
                      <p className="text-xs text-slate-400">{type}</p>
                    </td>
                    <td>
                      <label className="inline-flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={enabled}
                          disabled={!canEdit}
                          onChange={(e) => save(type, { enabled: e.target.checked })}
                        />
                        {enabled ? "Sí" : "No"}
                      </label>
                    </td>
                    <td className="max-w-[180px]">
                      {canEdit ? (
                        <Select value={severity} onChange={(e) => save(type, { severity: e.target.value })}>
                          <option value="">Por defecto ({DEFAULTS[type]})</option>
                          <option value="info">info</option>
                          <option value="warning">warning</option>
                          <option value="critical">critical</option>
                        </Select>
                      ) : (
                        <Badge tone={SEVERITY_TONE[severity || DEFAULTS[type]]}>{severity || DEFAULTS[type]}</Badge>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Las reglas por dispositivo (que tienen prioridad) se gestionan desde la API o con tools/manage_events.py.
        </p>
      </Card>
    </>
  );
}
