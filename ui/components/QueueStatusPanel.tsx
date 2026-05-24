import type {
  OutboxQueueRow,
  ProjectOutboxStatus,
  SourceLifecycleEventStatus,
  SourceRetractionStatus,
} from "../lib/api";

export interface QueueStatusPanelProps {
  outbox: ProjectOutboxStatus;
  sourceRetractions: SourceRetractionStatus;
  isLoading?: boolean;
  errorMessage?: string | null;
}

type QueueState = "clear" | "attention";

function statusClass(status: QueueState): string {
  return `pfos-status pfos-status-${status}`;
}

function formatAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "No open age";
  }

  if (seconds < 60) {
    return `${seconds}s open`;
  }

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m open`;
  }

  const hours = Math.floor(minutes / 60);
  return `${hours}h open`;
}

function rowId(row: OutboxQueueRow): string {
  return row.outbox_id ?? row.id ?? "unavailable";
}

function eventId(event: SourceLifecycleEventStatus): string {
  return event.event_id ?? event.id ?? "unavailable";
}

function OutboxRows({
  title,
  count,
  rows,
  fallback,
}: {
  title: string;
  count: number;
  rows?: OutboxQueueRow[];
  fallback: string;
}) {
  return (
    <section className="pfos-queue-table-section" aria-label={title}>
      <header className="pfos-inline-section-header">
        <h4>{title}</h4>
        <span className={statusClass(count > 0 ? "attention" : "clear")}>
          {count > 0 ? `${count} open` : "Empty"}
        </span>
      </header>
      {rows && rows.length > 0 ? (
        <table className="pfos-queue-table">
          <thead>
            <tr>
              <th scope="col">Outbox ID</th>
              <th scope="col">Target</th>
              <th scope="col">Operation</th>
              <th scope="col">Errors</th>
              <th scope="col">Last error</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${rowId(row)}-${index}`}>
                <th scope="row">{rowId(row)}</th>
                <td>{row.target_store ?? "Unknown"}</td>
                <td>{row.operation_type ?? "Unknown"}</td>
                <td>{row.error_count ?? 0}</td>
                <td>{row.last_error ?? "None"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : count > 0 ? (
        <table className="pfos-queue-table">
          <tbody>
            <tr>
              <th scope="row">{fallback}</th>
              <td>{count}</td>
              <td>Row details are not exposed by the current status endpoint.</td>
            </tr>
          </tbody>
        </table>
      ) : (
        <p className="pfos-empty-state">No rows to show.</p>
      )}
    </section>
  );
}

function SourceLifecycleRows({
  title,
  count,
  events,
  fallback,
}: {
  title: string;
  count: number;
  events?: SourceLifecycleEventStatus[];
  fallback: string;
}) {
  return (
    <section className="pfos-queue-table-section" aria-label={title}>
      <header className="pfos-inline-section-header">
        <h4>{title}</h4>
        <span className={statusClass(count > 0 ? "attention" : "clear")}>
          {count > 0 ? `${count} open` : "Empty"}
        </span>
      </header>
      {events && events.length > 0 ? (
        <table className="pfos-queue-table">
          <thead>
            <tr>
              <th scope="col">Event ID</th>
              <th scope="col">Source</th>
              <th scope="col">Event</th>
              <th scope="col">Status</th>
              <th scope="col">Last error</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event, index) => (
              <tr key={`${eventId(event)}-${index}`}>
                <th scope="row">{eventId(event)}</th>
                <td>{event.source_id ?? "Unknown"}</td>
                <td>{event.event_type ?? "retracted"}</td>
                <td>{event.processing_status ?? "Unknown"}</td>
                <td>{event.last_error ?? "None"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : count > 0 ? (
        <table className="pfos-queue-table">
          <tbody>
            <tr>
              <th scope="row">{fallback}</th>
              <td>{count}</td>
              <td>Event details are not exposed by the current status endpoint.</td>
            </tr>
          </tbody>
        </table>
      ) : (
        <p className="pfos-empty-state">No events to show.</p>
      )}
    </section>
  );
}

export function QueueStatusPanel({
  outbox,
  sourceRetractions,
  isLoading = false,
  errorMessage = null,
}: QueueStatusPanelProps) {
  const hasQueueBlockers = outbox.blocked || sourceRetractions.blocked;
  const pendingOutboxCount = Math.max(
    outbox.unprocessed_count - outbox.failed_count,
    0,
  );
  const blockedLifecycleEvents = sourceRetractions.blocked_events ?? [];
  const blockedLifecycleCount =
    blockedLifecycleEvents.length > 0 ? blockedLifecycleEvents.length : 0;

  return (
    <section
      className="pfos-health-section"
      aria-labelledby="queue-status-heading"
      aria-busy={isLoading}
    >
      <header className="pfos-inline-section-header">
        <div>
          <h3 id="queue-status-heading">Queue status</h3>
          <p>Read-only outbox and source retraction cascade visibility.</p>
        </div>
        <span className={statusClass(hasQueueBlockers ? "attention" : "clear")}>
          {hasQueueBlockers ? "Blocked" : "Clear"}
        </span>
      </header>

      {isLoading ? <p className="pfos-empty-state">Loading queue status...</p> : null}
      {errorMessage ? (
        <p className="pfos-project-health-error" role="alert">
          {errorMessage}
        </p>
      ) : null}

      <dl className="pfos-field-list">
        <div>
          <dt>Outbox oldest open row</dt>
          <dd>{formatAge(outbox.oldest_unprocessed_age_seconds)}</dd>
        </div>
        <div>
          <dt>Retraction oldest open event</dt>
          <dd>{formatAge(sourceRetractions.oldest_open_age_seconds)}</dd>
        </div>
        <div>
          <dt>Processing retractions</dt>
          <dd>{sourceRetractions.processing_count}</dd>
        </div>
      </dl>

      <OutboxRows
        title="Pending outbox rows"
        count={pendingOutboxCount}
        rows={outbox.pending_rows}
        fallback="Pending outbox rows"
      />
      <OutboxRows
        title="Failed outbox rows"
        count={outbox.failed_count}
        rows={outbox.failed_rows}
        fallback="Failed outbox rows"
      />
      <SourceLifecycleRows
        title="Pending source retraction cascades"
        count={sourceRetractions.pending_count + sourceRetractions.processing_count}
        events={sourceRetractions.pending_events}
        fallback="Pending or processing retraction events"
      />
      <SourceLifecycleRows
        title="Failed source lifecycle events"
        count={sourceRetractions.failed_count}
        events={sourceRetractions.failed_events}
        fallback="Failed retraction events"
      />
      {blockedLifecycleCount > 0 ? (
        <SourceLifecycleRows
          title="Blocked source lifecycle events"
          count={blockedLifecycleCount}
          events={blockedLifecycleEvents}
          fallback="Blocked source lifecycle events"
        />
      ) : null}
    </section>
  );
}

export default QueueStatusPanel;
