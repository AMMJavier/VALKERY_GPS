import { useEffect, useState } from "react";
import { Button, Card, Empty, ErrorBox, PageHeader, Spinner, TimeText } from "../components/common/ui";
import { api } from "../services/api";

export function Audit() {
  const [items, setItems] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function load(next = null) {
    setLoading(true);
    try {
      const page = await api.audit({ limit: 50, cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <>
      <PageHeader title="Auditoría" subtitle="Inicios de sesión y cambios sensibles" />
      <Card>
        <ErrorBox error={error} />
        {!items.length && !loading ? (
          <Empty>Sin registros.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500">
                <tr>
                  <th className="py-2">Fecha</th>
                  <th>Acción</th>
                  <th>Usuario</th>
                  <th>Objeto</th>
                  <th>IP</th>
                  <th>Detalle</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((a) => (
                  <tr key={a.id}>
                    <td className="py-1.5 whitespace-nowrap">
                      <TimeText iso={a.created_at} />
                    </td>
                    <td className="font-medium">{a.action}</td>
                    <td>{a.actor_id ?? "—"}</td>
                    <td>{a.target_type ? `${a.target_type} ${a.target_id ?? ""}` : "—"}</td>
                    <td className="font-mono text-xs">{a.ip ?? "—"}</td>
                    <td className="max-w-xs truncate font-mono text-xs" title={JSON.stringify(a.details)}>
                      {Object.keys(a.details).length ? JSON.stringify(a.details) : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-3 flex justify-center">
          {loading ? <Spinner /> : cursor && <Button variant="secondary" onClick={() => load(cursor)}>Cargar más</Button>}
        </div>
      </Card>
    </>
  );
}
