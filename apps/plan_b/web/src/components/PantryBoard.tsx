// The pantry profile's stock and service board (runtime 1.1.0). It renders only what the state
// view's `stock` projection says, so the live board and the recorded replay show the same
// numbers. Two counters are deliberately kept apart: the pantry-controlled supply gap (what the
// pantry still lacks on hand for the remaining target) and the unfulfilled service target (the
// original target minus distribution recorded on time). Holds, plan commitments and receipts
// can close the gap; only staff-recorded distribution reduces the unfulfilled target.

import { fmtQuantity, fmtTime, lookups } from "../format";
import type { StatusLabel } from "../format";
import type {
  ConsumableStateView,
  EventStateView,
  HandoffTaskStatus,
  ServiceProgressView,
  StockBalanceView,
} from "../types";
import { EvidenceCard } from "./EvidenceCard";
import { Code, Empty, JumpButton, Section, StatusBadge, Tag, When, domId } from "./ui";

export const HANDOFF_STATUS_LABEL: Record<HandoffTaskStatus, StatusLabel> = {
  open: { text: "Open: waiting for staff", icon: "⧗", tone: "warn" },
  fulfilled: { text: "Handed off", icon: "✔", tone: "ok" },
  partially_fulfilled: { text: "Partly handed off", icon: "◐", tone: "warn" },
  lapsed: { text: "Lapsed", icon: "⧖", tone: "neutral" },
};

/** The state's consumable-stock projection, or null for a profile without consumable stock. */
export function stockOf(view: EventStateView): ConsumableStateView | null {
  return view.stock ?? null;
}

/** "opening 24 + received 16 − transferred 0 − distributed 0 = 40 on hand". */
export function conservationText(b: StockBalanceView): string {
  return (
    `opening ${b.opening_quantity} + received ${b.received_quantity} − transferred out ` +
    `${b.transferred_out_quantity} − distributed ${b.distributed_quantity} = ${b.on_hand_quantity} on hand`
  );
}

function Counter({
  id,
  label,
  value,
  note,
  tone,
}: {
  id: string;
  label: string;
  value: string;
  note: string;
  tone: "ok" | "warn" | "bad" | "neutral";
}) {
  return (
    <div className={`counter tone-line-${tone}`} data-counter={id}>
      <dt>{label}</dt>
      <dd>
        <span className="counter-value">{value}</span>
        <span className="sub">{note}</span>
      </dd>
    </div>
  );
}

/** One service target: its two separate counters, achieved service and staffed capacity. */
export function ServiceTargetCard({ service, view }: { service: ServiceProgressView; view: EventStateView }) {
  const tz = view.timezone;
  const look = lookups(view);
  const unit = service.unit;
  return (
    <div className="service-target" data-service-target={service.target_id}>
      <h3 className="list-heading">
        Target <Code>{service.target_id}</Code>: {fmtQuantity(service.original_quantity, unit)} by{" "}
        <When iso={service.deadline} text={fmtTime(service.deadline, tz)} /> ({look.activityLabel(service.activity_id)}){" "}
        {service.attained ? (
          <Tag tone="ok" icon="✔">
            Attained on time
          </Tag>
        ) : null}
      </h3>
      {service.target_quantity !== service.original_quantity ? (
        <p className="small tone-text-warn">
          The current goal version targets {fmtQuantity(service.target_quantity, unit)}; attainment is still scored
          against the original {fmtQuantity(service.original_quantity, unit)}.
        </p>
      ) : null}
      <dl className="counter-grid">
        <Counter
          id="supply_gap"
          label="Pantry-controlled supply gap"
          value={fmtQuantity(service.supply_gap_quantity, unit)}
          note="Still lacking on hand for the remaining target. A recorded receipt closes it; expected units do not."
          tone={service.supply_gap_quantity > 0 ? "warn" : "ok"}
        />
        <Counter
          id="unfulfilled"
          label="Unfulfilled service target"
          value={fmtQuantity(service.unfulfilled_quantity, unit)}
          note="Original target minus distribution recorded on time. Holds, plans and receipts never reduce it."
          tone={service.unfulfilled_quantity > 0 ? "bad" : "ok"}
        />
        <Counter
          id="achieved"
          label="Achieved service (staff-recorded)"
          value={`${service.on_time_quantity} of ${service.original_quantity} on time`}
          note={service.late_quantity > 0 ? `${service.late_quantity} more recorded late (not on time)` : "No late distribution"}
          tone={service.attained ? "ok" : "neutral"}
        />
        <Counter
          id="committed"
          label="Committed, not yet distributed"
          value={fmtQuantity(service.committed_quantity, unit)}
          note="Reserved by the applied plan; serves nobody until staff record a distribution."
          tone="neutral"
        />
        <Counter
          id="capacity"
          label="Staffed capacity so far"
          value={fmtQuantity(service.capacity_quantity, unit)}
          note={`${service.qualified_minutes} staffed minutes with committed stock, minus what is already distributed.`}
          tone="neutral"
        />
      </dl>
    </div>
  );
}

/** Each pool's on-hand, reserved and available quantities, with its conservation terms. */
export function StockTable({ stock, view }: { stock: ConsumableStateView; view: EventStateView }) {
  const look = lookups(view);
  if (stock.balances.length === 0) return <Empty>No consumable stock is registered.</Empty>;
  return (
    <div className="table-scroll">
      <table className="stock-table">
        <caption className="sr-only">Stock pools</caption>
        <thead>
          <tr>
            <th scope="col">Pool</th>
            <th scope="col">On hand</th>
            <th scope="col">Reserved</th>
            <th scope="col">Available</th>
            <th scope="col">Expected (not stock)</th>
            <th scope="col">Distributed</th>
          </tr>
        </thead>
        <tbody>
          {stock.balances.map((b) => (
            <tr key={b.resource_id} data-stock={b.resource_id}>
              <th scope="row">
                {look.resourceLabel(b.resource_id)} <span className="muted small">({b.resource_id})</span>
                <span className={`sub ${b.conserved ? "" : "tone-text-bad"}`}>
                  {b.conserved ? "✓ " : "✖ not conserved: "}
                  {conservationText(b)}
                </span>
              </th>
              <td data-quantity="on_hand">{b.on_hand_quantity}</td>
              <td data-quantity="reserved">
                {b.reserved_quantity}
                <span className="sub">
                  {b.held_quantity} held, {b.committed_quantity} committed
                </span>
              </td>
              <td data-quantity="available">{b.available_quantity}</td>
              <td data-quantity="expected">{b.expected_quantity}</td>
              <td data-quantity="distributed">{b.distributed_quantity}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Quantities in {stock.balances[0] !== undefined ? stock.balances[0].unit.replace(/_/g, " ") : "units"}. On hand
        includes reserved units; available = on hand − reserved. A hold or a plan moves no stock; only a staff-recorded
        receipt or distribution does.
      </p>
    </div>
  );
}

export function PantryBoard({ view }: { view: EventStateView }) {
  const stock = stockOf(view);
  const tz = view.timezone;
  const look = lookups(view);
  if (stock === null) return null;
  return (
    <Section
      id="pantry-board"
      title="Stock and service"
      subtitle="Fictional kits. Physical receipt and distribution are staff attestations; the coordinator agent cannot record them."
    >
      {stock.service.length === 0 ? (
        <Empty>No service target is defined.</Empty>
      ) : (
        stock.service.map((s) => <ServiceTargetCard key={s.target_id} service={s} view={view} />)
      )}
      <h3 className="list-heading">Stock pools</h3>
      <StockTable stock={stock} view={view} />
      <h3 className="list-heading">Expected shipments ({stock.expected_shipments.length})</h3>
      {stock.expected_shipments.length === 0 ? (
        <Empty>No shipment is expected.</Empty>
      ) : (
        <ul className="fact-list small">
          {stock.expected_shipments.map((e) => (
            <li key={e.shipment.shipment_id} data-shipment={e.shipment.shipment_id}>
              <strong>Shipment {e.shipment.shipment_id}</strong> into {look.resourceLabel(e.shipment.destination_resource_id)}:{" "}
              {e.shipment.quantity} expected
              {e.shipment.expected_at !== null ? (
                <>
                  {" "}at <When iso={e.shipment.expected_at} text={fmtTime(e.shipment.expected_at, tz)} />
                </>
              ) : null}
              {e.reported_eta !== null ? (
                <>
                  , latest reported ETA <When iso={e.reported_eta} text={fmtTime(e.reported_eta, tz)} />
                  {e.status_observation_id !== null ? (
                    <>
                      {" "}(
                      <JumpButton targetId={domId("obs", e.status_observation_id)}>{e.status_observation_id}</JumpButton>)
                    </>
                  ) : null}
                </>
              ) : null}
              ; received {e.shipment.received_quantity}, <strong>outstanding {e.outstanding_quantity}</strong>.{" "}
              <span className="muted">Expected units are not on hand until staff record their receipt.</span>
            </li>
          ))}
        </ul>
      )}
      <h3 className="list-heading">Staff handoff tasks ({stock.handoff_tasks.length})</h3>
      {stock.handoff_tasks.length === 0 ? (
        <Empty>No handoff has been requested.</Empty>
      ) : (
        <ul className="fact-list small">
          {stock.handoff_tasks.map((t) => (
            <li key={t.hold_id} data-handoff-task={t.hold_id}>
              <StatusBadge label={HANDOFF_STATUS_LABEL[t.status] ?? { text: t.status, icon: "•", tone: "neutral" }} />{" "}
              {t.requested_quantity} from {look.resourceLabel(t.source_resource_id)} into{" "}
              {look.resourceLabel(t.destination_resource_id)} (hold <Code>{t.hold_id}</Code>), {t.remaining_quantity} still
              reserved for it; requested <When iso={t.requested_at} text={fmtTime(t.requested_at, tz)} />, hand off before{" "}
              <When iso={t.cutoff} text={fmtTime(t.cutoff, tz)} />
              {t.stock_receipt_ids.length > 0 ? <> · receipts {t.stock_receipt_ids.join(", ")}</> : null}
            </li>
          ))}
        </ul>
      )}
      <h3 className="list-heading">Committed allocations ({stock.allocations.length})</h3>
      {stock.allocations.length === 0 ? (
        <Empty>Nothing is committed to distribution yet.</Empty>
      ) : (
        <ul className="fact-list small">
          {stock.allocations.map((a) => (
            <li key={a.allocation_id}>
              <Code>{a.allocation_id}</Code>: {a.quantity} of {look.resourceLabel(a.resource_id)} for{" "}
              <Code>{a.service_target_id}</Code>, {a.remaining_quantity} not yet distributed (plan v{a.plan_version}, from
              hold <Code>{a.source_hold_id}</Code>)
            </li>
          ))}
        </ul>
      )}
      <h3 className="list-heading">Staff-recorded receipts and distributions</h3>
      {stock.receipts.length === 0 && stock.distributions.length === 0 ? (
        <Empty>No physical record yet.</Empty>
      ) : (
        <ul className="fact-list small">
          {stock.receipts.map((r) => (
            <li key={r.stock_receipt_id}>
              <Tag tone="info" icon="⇉">
                Receipt
              </Tag>{" "}
              <Code>{r.receipt_reference}</Code>: {r.quantity} into {look.resourceLabel(r.resource_id)}
              {r.source_resource_id !== null ? <> from {look.resourceLabel(r.source_resource_id)}</> : null}
              {r.shipment_id !== null ? <> (shipment {r.shipment_id})</> : null} at{" "}
              <When iso={r.at} text={fmtTime(r.at, tz)} /> by <Code>{r.actor_id}</Code> (receipt{" "}
              <JumpButton targetId={domId("rcpt", r.receipt_id)}>{r.receipt_id}</JumpButton>)
            </li>
          ))}
          {stock.distributions.map((d) => (
            <li key={d.distribution_id}>
              <Tag tone={d.on_time ? "ok" : "warn"} icon={d.on_time ? "✔" : "⧖"}>
                {d.on_time ? "Distributed on time" : "Distributed late"}
              </Tag>{" "}
              <Code>{d.distribution_reference}</Code>: {d.quantity} of {look.resourceLabel(d.resource_id)} for{" "}
              <Code>{d.service_target_id}</Code> at <When iso={d.at} text={fmtTime(d.at, tz)} /> by <Code>{d.actor_id}</Code>{" "}
              (receipt <JumpButton targetId={domId("rcpt", d.receipt_id)}>{d.receipt_id}</JumpButton>)
            </li>
          ))}
        </ul>
      )}
      <EvidenceCard title={`Stock ledger (${stock.movements.length} movements, JSON)`} value={stock.movements} />
    </Section>
  );
}
