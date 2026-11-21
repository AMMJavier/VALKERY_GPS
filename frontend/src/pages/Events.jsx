import { useEffect, useState } from "react";
import { EventList } from "../components/common/EventList";
import { Button, Card, ErrorBox, Field, Input, PageHeader, Select, Spinner } from "../components/common/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { localInputToIso } from "../utils/format";
import { EVENT_LABELS } from "../utils/status";

const PAGE = 50;

export function Events() {
  const devices = useAsync(() => api.devices(), []);
  const [filters, setFilters] = useState({ device_id: "", event_type: "", severity: "", from: "", to: "" });
  const [items, setItems] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function load(nextCursor = null) {
    setLoading(true);
    setError(null);
    try {
      const page = await api.events({
        device_id: filters.device_id,
        event_type: filters.event_type,
        severity: filters.severity,
        from: localInputToIso(filters.from),
        to: localInputToIso(filters.to),
        limit: PAGE,
        cursor: nextCursor,
      });
      setItems((prev) => (nextCursor ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const deviceMap = Object.fromEntries((devices.data ?? []).map((d) => [d.id, d]));
  const set = (key) => (e) => setFilters({ ...filters, [key]: e.target.value });

  return (
    <>
      <PageHeader title="Eventos" subtitle="Más recientes primero" />
      <Card className="mb-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            load();
          }}
          className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-6"
        >
          <Field label="Dispositivo">
            <Select value={filters.device_id} onChange={set("device_id")}>
              <option value="">Todos</option>
              {(devices.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Tipo">
            <Select value={filters.event_type} onChange={set("event_type")}>
              <option value="">Todos</option>
              {Object.entries(EVENT_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Severidad">
            <Select value={filters.severity} onChange={set("severity")}>
              <option value="">Todas</option>
              <option value="critical">critical</option>
              <option value="warning">warning</option>
              <option value="info">info</option>
            </Select>
          </Field>
          <Field label="Desde">
            <Input type="datetime-local" value={filters.from} onChange={set("from")} />
          </Field>
          <Field label="Hasta">
            <Input type="datetime-local" value={filters.to} onChange={set("to")} />
          </Field>
          <Button type="submit" disabled={loading}>
            Filtrar
          </Button>
        </form>
      </Card>
      <Card>
        <ErrorBox error={error} />
        <EventList events={items} devices={deviceMap} />
        <div className="mt-3 flex justify-center">
          {loading ? (
            <Spinner />
          ) : (
            cursor && (
              <Button variant="secondary" onClick={() => load(cursor)}>
                Cargar más
              </Button>
            )
          )}
        </div>
      </Card>
    </>
  );
}
