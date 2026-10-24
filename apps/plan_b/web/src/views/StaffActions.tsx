// The staff session's view (W2.3): staff attest physical facts the coordinator agent cannot.
// `record_stock_receipt` records a handoff from a held alternate pool (or a matched external
// shipment) and `record_distribution` records an aggregate, completed distribution of committed
// stock. Both go through the common tool endpoint with the staff session's own grant, one
// idempotency key per submission, the board's revision (and goal version for distributions),
// and a physical reference that the server keeps unique whatever the request key.

import { useId, useState } from "react";
import type { FormEvent } from "react";

import { buildToolRequest } from "../api";
import type { StoredSession, ToolBinding } from "../api";
import { stockOf } from "../components/PantryBoard";
import { Code, Empty, Section, Tag, When } from "../components/ui";
import { compareIso, fmtQuantity, fmtTime, lookups } from "../format";
import type {
  ConsumableStateView,
  EventStateView,
  GrantView,
  JsonObject,
  ObservationRecord,
  ServiceProgressView,
  StaffTool,
} from "../types";
import { STAFF_TOOLS } from "../types";
import { SubmissionList } from "../panels/MutationStatus";
import type { MutationTracker } from "../panels/useMutations";
import { Participation } from "./Participation";

const REFERENCE = /^[A-Za-z0-9_.:-]{1,128}$/;

/** The staff tools this session's grant allows. */
export function staffToolsOf(grant: GrantView | undefined): StaffTool[] {
  return grant === undefined ? [] : STAFF_TOOLS.filter((t) => grant.grant.allowed_tools.includes(t));
}

/** "handoff_002": the next numbered reference not yet used by a recorded physical record. */
export function nextReference(prefix: string, used: readonly string[]): string {
  for (let n = 1; ; n += 1) {
    const candidate = `${prefix}_${String(n).padStart(3, "0")}`;
    if (!used.includes(candidate)) return candidate;
  }
}

/** A whole number of at least 1, or null (fractional, negative and empty input are refused). */
export function wholeQuantity(text: string): number | null {
  if (!/^\d+$/.test(text.trim())) return null;
  const n = Number(text.trim());
  return Number.isSafeInteger(n) && n >= 1 ? n : null;
}

/** Observations that concern one of the given entities, newest first (the receipt cites one). */
export function observationsAbout(view: EventStateView, entityIds: readonly string[]): ObservationRecord[] {
  return view.observations
    .filter((o) => entityIds.includes(o.observation.entity_id))
    .sort((a, b) => compareIso(b.observation.received_at, a.observation.received_at));
}

export type ReceiptSource =
  | { readonly kind: "handoff"; readonly holdId: string }
  | { readonly kind: "shipment"; readonly shipmentId: string };

/** Open handoff tasks: live stock-transfer holds with units still reserved for staff. */
export function openHandoffs(stock: ConsumableStateView) {
  return stock.handoff_tasks.filter(
    (t) => t.remaining_quantity > 0 && (t.status === "open" || t.status === "partially_fulfilled"),
  );
}

/** record_stock_receipt arguments for the chosen source, or why they cannot be sent. */
export function receiptArguments(
  view: EventStateView,
  source: ReceiptSource | null,
  quantityText: string,
  observationId: string,
  reference: string,
): { ok: true; args: JsonObject } | { ok: false; reason: string } {
  const stock = stockOf(view);
  if (stock === null || source === null) return { ok: false, reason: "Choose a handoff task or a shipment." };
  const quantity = wholeQuantity(quantityText);
  if (quantity === null) return { ok: false, reason: "The quantity must be a whole number of at least 1." };
  if (observationId === "") return { ok: false, reason: "Cite the observation this receipt rests on." };
  if (!REFERENCE.test(reference)) {
    return { ok: false, reason: "The receipt reference must be 1-128 letters, digits, '_', '.', ':' or '-'." };
  }
  if (source.kind === "handoff") {
    const task = stock.handoff_tasks.find((t) => t.hold_id === source.holdId);
    if (task === undefined) return { ok: false, reason: `Hold ${source.holdId} is not a handoff task.` };
    const unit = stock.balances.find((b) => b.resource_id === task.destination_resource_id)?.unit ?? "";
    return {
      ok: true,
      args: {
        resource_id: task.destination_resource_id,
        quantity,
        unit,
        source_observation_id: observationId,
        receipt_reference: reference,
        source_resource_id: task.source_resource_id,
        source_hold_id: task.hold_id,
      },
    };
  }
  const shipment = stock.expected_shipments.find((e) => e.shipment.shipment_id === source.shipmentId);
  if (shipment === undefined) return { ok: false, reason: `Shipment ${source.shipmentId} is not registered.` };
  const destination = shipment.shipment.destination_resource_id;
  const unit = stock.balances.find((b) => b.resource_id === destination)?.unit ?? "";
  return {
    ok: true,
    args: {
      resource_id: destination,
      quantity,
      unit,
      source_observation_id: observationId,
      receipt_reference: reference,
      shipment_id: shipment.shipment.shipment_id,
    },
  };
}

/** The most staff can record for a target now: committed stock, the remaining target, capacity. */
export function distributableNow(service: ServiceProgressView, committed: number): number {
  const remaining = service.original_quantity - service.distributed_quantity;
  return Math.max(0, Math.min(committed, remaining, service.capacity_quantity));
}

function ReceiptForm({
  view,
  stock,
  binding,
  tracker,
}: {
  view: EventStateView;
  stock: ConsumableStateView;
  binding: ToolBinding;
  tracker: MutationTracker;
}) {
  const formId = useId();
  const tz = view.timezone;
  const look = lookups(view);
  const tasks = openHandoffs(stock);
  const shipments = stock.expected_shipments.filter((e) => e.outstanding_quantity > 0);
  const [choice, setChoice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [observation, setObservation] = useState("");
  const [reference, setReference] = useState("");
  const options = [
    ...tasks.map((t) => ({ key: `hold:${t.hold_id}`, source: { kind: "handoff", holdId: t.hold_id } as ReceiptSource })),
    ...shipments.map((e) => ({
      key: `shipment:${e.shipment.shipment_id}`,
      source: { kind: "shipment", shipmentId: e.shipment.shipment_id } as ReceiptSource,
    })),
  ];
  const chosen = options.find((o) => o.key === choice) ?? options[0];
  const source = chosen?.source ?? null;
  const task = source?.kind === "handoff" ? tasks.find((t) => t.hold_id === source.holdId) : undefined;
  const shipment =
    source?.kind === "shipment" ? shipments.find((e) => e.shipment.shipment_id === source.shipmentId) : undefined;
  const entities = task !== undefined
    ? [task.source_resource_id, task.destination_resource_id]
    : shipment !== undefined
      ? [shipment.shipment.destination_resource_id]
      : [];
  const cited = observationsAbout(view, entities);
  const defaultQuantity = String(task?.remaining_quantity ?? shipment?.outstanding_quantity ?? "");
  const used = stock.receipts.map((r) => r.receipt_reference);
  const defaultReference = nextReference(source?.kind === "shipment" ? "receipt" : "handoff", used);
  const quantityText = quantity !== "" ? quantity : defaultQuantity;
  const observationId = observation !== "" && cited.some((o) => o.observation.observation_id === observation)
    ? observation
    : (cited[0]?.observation.observation_id ?? "");
  const referenceText = reference !== "" ? reference : defaultReference;
  const built = receiptArguments(view, source, quantityText, observationId, referenceText);
  const sending = tracker.isSending("staff", "record_stock_receipt");
  const destination = task?.destination_resource_id ?? shipment?.shipment.destination_resource_id;
  const unit = stock.balances.find((b) => b.resource_id === destination)?.unit ?? "unit";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!built.ok) return;
    const request = buildToolRequest(binding, "record_stock_receipt", built.args, {
      idempotent: true,
      expectedRevision: view.revision,
    });
    const what =
      task !== undefined
        ? `${built.args.quantity} from ${look.resourceLabel(task.source_resource_id)}`
        : `${built.args.quantity} of shipment ${shipment?.shipment.shipment_id ?? ""}`;
    tracker.submit("staff", `Receipt ${referenceText}: ${what}`, request);
    setQuantity("");
    setReference("");
  };

  return (
    <form className="form" onSubmit={submit} aria-labelledby={`${formId}-receipt`}>
      <h3 className="list-heading" id={`${formId}-receipt`}>
        Record a stock receipt
      </h3>
      {options.length === 0 ? (
        <Empty>No handoff is waiting for staff and no shipment is outstanding.</Empty>
      ) : (
        <>
          <label className="field">
            <span>What arrived</span>
            <select value={chosen?.key ?? ""} onChange={(e) => setChoice(e.target.value)}>
              {tasks.map((t) => (
                <option key={t.hold_id} value={`hold:${t.hold_id}`}>
                  {`Handoff ${t.hold_id}: ${t.remaining_quantity} from ${look.resourceLabel(t.source_resource_id)} into ${look.resourceLabel(t.destination_resource_id)}`}
                </option>
              ))}
              {shipments.map((e) => (
                <option key={e.shipment.shipment_id} value={`shipment:${e.shipment.shipment_id}`}>
                  {`Shipment ${e.shipment.shipment_id}: ${e.outstanding_quantity} outstanding into ${look.resourceLabel(e.shipment.destination_resource_id)}`}
                </option>
              ))}
            </select>
          </label>
          {task !== undefined ? (
            <p className="small muted">
              Hold <Code>{task.hold_id}</Code> reserves {fmtQuantity(task.remaining_quantity, unit)} of{" "}
              {look.resourceLabel(task.source_resource_id)} for this handoff; hand off before{" "}
              <When iso={task.cutoff} text={fmtTime(task.cutoff, tz)} /> (exclusive). A partial handoff keeps the rest
              reserved.
            </p>
          ) : null}
          <label className="field">
            <span>Quantity handed over (whole {unit.replace(/_/g, " ")}s)</span>
            <input inputMode="numeric" value={quantityText} onChange={(e) => setQuantity(e.target.value)} />
          </label>
          <label className="field">
            <span>Evidence (observation)</span>
            <select value={observationId} onChange={(e) => setObservation(e.target.value)}>
              {cited.length === 0 ? <option value="">No observation about these pools</option> : null}
              {cited.map((o) => (
                <option key={o.observation.observation_id} value={o.observation.observation_id}>
                  {`${o.observation.observation_id} (${o.observation.entity_id}, ${fmtTime(o.observation.received_at, tz)}): ${o.observation.text.slice(0, 60)}`}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Receipt reference (from the paper record)</span>
            <input value={referenceText} maxLength={128} onChange={(e) => setReference(e.target.value)} />
          </label>
          {!built.ok ? (
            <p className="small tone-text-warn" role="status">
              {built.reason} Nothing is sent until this is fixed.
            </p>
          ) : (
            <p className="consequence small">
              <strong>Records now</strong> (scenario clock <When iso={view.clock} text={fmtTime(view.clock, tz)} />) that{" "}
              {fmtQuantity(Number(built.args.quantity), unit)} physically arrived in{" "}
              {look.resourceLabel(String(built.args.resource_id))}
              {task !== undefined ? <> from {look.resourceLabel(task.source_resource_id)}</> : null}. The server debits
              and credits the pools in one transaction and refuses a reference it has already recorded.
            </p>
          )}
          <button type="submit" className="button" disabled={sending || !built.ok}>
            {sending ? "Recording receipt…" : "Record stock receipt"}
          </button>
        </>
      )}
    </form>
  );
}

function DistributionForm({
  view,
  stock,
  binding,
  tracker,
}: {
  view: EventStateView;
  stock: ConsumableStateView;
  binding: ToolBinding;
  tracker: MutationTracker;
}) {
  const formId = useId();
  const tz = view.timezone;
  const look = lookups(view);
  const [targetId, setTargetId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reference, setReference] = useState("");
  const service = stock.service.find((s) => s.target_id === targetId) ?? stock.service[0];
  const allocations = stock.allocations.filter(
    (a) => service !== undefined && a.service_target_id === service.target_id && a.remaining_quantity > 0,
  );
  const committed = allocations.reduce((sum, a) => sum + a.remaining_quantity, 0);
  const pool = allocations[0]?.resource_id ?? null;
  const unit = service?.unit ?? "unit";
  const activity = view.activities.find((a) => a.definition.activity_id === service?.activity_id);
  const started = activity !== undefined && (activity.lifecycle === "started" || activity.lifecycle === "completed");
  const most = service !== undefined ? distributableNow(service, committed) : 0;
  const quantityText = quantity !== "" ? quantity : most > 0 ? String(most) : "";
  const parsed = wholeQuantity(quantityText);
  const used = stock.distributions.map((d) => d.distribution_reference);
  const referenceText = reference !== "" ? reference : nextReference("distribution", used);
  const onTime = service !== undefined && compareIso(view.clock, service.deadline) <= 0;
  const sending = tracker.isSending("staff", "record_distribution");
  const problem =
    service === undefined
      ? "No service target is defined."
      : pool === null
        ? "Nothing is committed to this target yet; only committed stock is distributed."
        : parsed === null
          ? "The quantity must be a whole number of at least 1."
          : !REFERENCE.test(referenceText)
            ? "The distribution reference must be 1-128 letters, digits, '_', '.', ':' or '-'."
            : null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (problem !== null || service === undefined || pool === null || parsed === null) return;
    const args: JsonObject = {
      resource_id: pool,
      quantity: parsed,
      unit,
      service_target_id: service.target_id,
      activity_id: service.activity_id,
      distribution_reference: referenceText,
      allocation_ids: allocations.map((a) => a.allocation_id),
    };
    const request = buildToolRequest(binding, "record_distribution", args, {
      idempotent: true,
      expectedRevision: view.revision,
      expectedGoalVersion: view.goal.version,
    });
    tracker.submit("staff", `Distribution ${referenceText}: ${parsed} for ${service.target_id}`, request);
    setQuantity("");
    setReference("");
  };

  return (
    <form className="form" onSubmit={submit} aria-labelledby={`${formId}-distribution`}>
      <h3 className="list-heading" id={`${formId}-distribution`}>
        Record a distribution
      </h3>
      {stock.service.length > 1 ? (
        <label className="field">
          <span>Service target</span>
          <select value={service?.target_id ?? ""} onChange={(e) => setTargetId(e.target.value)}>
            {stock.service.map((s) => (
              <option key={s.target_id} value={s.target_id}>
                {s.target_id}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {service !== undefined ? (
        <p className="small">
          Target <Code>{service.target_id}</Code>: {service.on_time_quantity} of {service.original_quantity} distributed on
          time; {fmtQuantity(committed, unit)} committed and not yet distributed; staffed capacity so far{" "}
          {fmtQuantity(service.capacity_quantity, unit)}. {activity !== undefined ? look.activityLabel(activity.definition.activity_id) : "The service"}{" "}
          {started ? (
            <>has {activity?.lifecycle}.</>
          ) : (
            <>
              has not started; staff record a distribution only once it has.{" "}
              <Tag tone="warn" icon="⧗">
                Not started
              </Tag>
            </>
          )}
        </p>
      ) : null}
      <label className="field">
        <span>Quantity distributed (whole {unit.replace(/_/g, " ")}s)</span>
        <input inputMode="numeric" value={quantityText} onChange={(e) => setQuantity(e.target.value)} />
      </label>
      <label className="field">
        <span>Distribution reference (from the paper record)</span>
        <input value={referenceText} maxLength={128} onChange={(e) => setReference(e.target.value)} />
      </label>
      {service !== undefined ? (
        <p className={`small ${onTime ? "" : "tone-text-warn"}`}>
          Recorded now at <When iso={view.clock} text={fmtTime(view.clock, tz)} />:{" "}
          {onTime ? (
            <>counts on time (deadline {fmtTime(service.deadline, tz)}, inclusive).</>
          ) : (
            <>
              after the {fmtTime(service.deadline, tz)} deadline. It is recorded truthfully as late and does not count on
              time.
            </>
          )}{" "}
          It consumes committed stock from allocations {allocations.map((a) => a.allocation_id).join(", ") || "none"}.
        </p>
      ) : null}
      {problem !== null ? (
        <p className="small tone-text-warn" role="status">
          {problem} Nothing is sent until this is fixed.
        </p>
      ) : null}
      <button type="submit" className="button" disabled={sending || problem !== null}>
        {sending ? "Recording distribution…" : "Record distribution"}
      </button>
    </form>
  );
}

export function StaffActions({
  view,
  binding,
  tracker,
}: {
  view: EventStateView;
  binding: ToolBinding;
  tracker: MutationTracker;
}) {
  const grant = view.grants.find((g) => g.grant.grant_id === view.viewer.grant_id);
  const tools = staffToolsOf(grant);
  const stock = stockOf(view);
  return (
    <Section
      id="staff-panel"
      title="Staff actions"
      className="panel"
      subtitle={
        <>
          You are <strong>{view.viewer.display_name}</strong>. Only staff attest that stock physically arrived or
          was distributed; the coordinator agent can request a handoff but cannot record it.
        </>
      }
    >
      {grant !== undefined && !grant.valid_now ? (
        <p className="notice tone-warn">
          <span aria-hidden="true">⚠ </span>
          Your grant is {grant.revoked ? "revoked" : "not valid at the current scenario time"}. The server will
          reject new records; the rejection will be shown here.
        </p>
      ) : null}
      {stock === null ? (
        <Empty>This event has no consumable stock to record.</Empty>
      ) : (
        <>
          {tools.includes("record_stock_receipt") ? (
            <ReceiptForm view={view} stock={stock} binding={binding} tracker={tracker} />
          ) : null}
          {tools.includes("record_distribution") ? (
            <DistributionForm view={view} stock={stock} binding={binding} tracker={tracker} />
          ) : null}
        </>
      )}
      <SubmissionList tracker={tracker} panel="staff" view={view} />
    </Section>
  );
}

/** A staff session's panel: tabs for the staff actions and the participant view. */
export function StaffWorkspace({
  view,
  binding,
  tracker,
  session,
}: {
  view: EventStateView;
  binding: ToolBinding;
  tracker: MutationTracker;
  session?: StoredSession;
}) {
  const [tab, setTab] = useState<"staff" | "role">("staff");
  const tabsId = useId();
  const tabs: { key: "staff" | "role"; label: string }[] = [
    { key: "staff", label: "Staff actions" },
    { key: "role", label: "Updates" },
  ];
  return (
    <div className="workspace">
      <div className="tabs" role="tablist" aria-label="Staff session">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            id={`${tabsId}-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`${tabsId}-${t.key}-panel`}
            className={`tab${tab === t.key ? " tab-selected" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${tabsId}-${tab}-panel`} aria-labelledby={`${tabsId}-${tab}`}>
        {tab === "staff" ? (
          <StaffActions view={view} binding={binding} tracker={tracker} />
        ) : (
          <Participation view={view} binding={binding} tracker={tracker} session={session} />
        )}
      </div>
    </div>
  );
}
