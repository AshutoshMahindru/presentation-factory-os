import type {
  HardGateCheck,
  ProjectControlPlaneHealth,
} from "../lib/api";

type ReadinessStatus = "ready" | "blocked" | "warning" | "unknown";

export interface ExportSlideSnapshot {
  slide_id?: string | null;
  visual_quality?: string | null;
  materiality?: string | null;
  content?: {
    body?: string | null;
    evidence_refs?: string[] | null;
    financial_refs?: string[] | null;
  } | null;
}

export interface ExportFinancialCellSnapshot {
  cell_ref?: string | null;
  validation_status?: string | null;
  status?: string | null;
}

export interface ExportArtifactSnapshot {
  id?: string | null;
  status?: string | null;
}

export interface ExportMetadataSnapshot {
  slide_id_to_claim_refs?: Record<string, string[]> | null;
  claim_refs_to_source_refs?: Record<string, string[]> | null;
  financial_refs_to_financial_cells?: Record<string, ExportFinancialCellSnapshot> | null;
}

export interface ExportDeckSnapshot {
  slides?: ExportSlideSnapshot[] | null;
  financial_validation_status?: string | null;
  unsupported_financial_claim_count?: number | null;
  financial_cells?:
    | Record<string, ExportFinancialCellSnapshot>
    | ExportFinancialCellSnapshot[]
    | null;
  artifacts?: ExportArtifactSnapshot[] | null;
  pending_source_retraction_count?: number | null;
  unprocessed_outbox_count?: number | null;
  export_metadata?: ExportMetadataSnapshot | null;
}

export interface ExportReadinessItem {
  id: string;
  label: string;
  status: ReadinessStatus;
  detail: string;
}

export interface ExportReadinessSection {
  id: string;
  title: string;
  status: ReadinessStatus;
  items: ExportReadinessItem[];
}

export interface ExportReadinessPanelProps {
  projectId: string;
  health?: ProjectControlPlaneHealth | null;
  deck?: ExportDeckSnapshot | null;
  exportMetadata?: ExportMetadataSnapshot | null;
  isLoading?: boolean;
  errorMessage?: string | null;
  onRefresh?: () => void;
}

interface ReadinessModel {
  headline: string;
  status: ReadinessStatus;
  sections: ExportReadinessSection[];
  blockers: ExportReadinessItem[];
  warnings: ExportReadinessItem[];
  unknowns: ExportReadinessItem[];
}

function statusClass(status: ReadinessStatus): string {
  return `pfos-status pfos-status-${status}`;
}

function item(
  id: string,
  label: string,
  status: ReadinessStatus,
  detail: string,
): ExportReadinessItem {
  return { id, label, status, detail };
}

function section(
  id: string,
  title: string,
  items: ExportReadinessItem[],
): ExportReadinessSection {
  return {
    id,
    title,
    status: sectionStatus(items),
    items,
  };
}

function sectionStatus(items: ExportReadinessItem[]): ReadinessStatus {
  if (items.some((readinessItem) => readinessItem.status === "blocked")) {
    return "blocked";
  }

  if (items.some((readinessItem) => readinessItem.status === "warning")) {
    return "warning";
  }

  if (items.some((readinessItem) => readinessItem.status === "unknown")) {
    return "unknown";
  }

  return "ready";
}

function slideId(slide: ExportSlideSnapshot, index: number): string {
  return slide.slide_id || `slide_${index + 1}`;
}

function materialSlides(slides: ExportSlideSnapshot[]): ExportSlideSnapshot[] {
  return slides.filter(
    (slide) => slide.materiality === "high" || slide.materiality === "medium",
  );
}

function stringList(values: string[] | null | undefined): string[] {
  return Array.isArray(values) ? values.filter((value) => value.length > 0) : [];
}

function numericCount(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function financialCellLookup(
  deck: ExportDeckSnapshot | null | undefined,
  exportMetadata: ExportMetadataSnapshot | null | undefined,
): Record<string, ExportFinancialCellSnapshot> {
  const metadataCells = exportMetadata?.financial_refs_to_financial_cells;
  if (metadataCells) {
    return metadataCells;
  }

  const cells = deck?.financial_cells;
  if (!cells) {
    return {};
  }

  if (!Array.isArray(cells)) {
    return cells;
  }

  return cells.reduce<Record<string, ExportFinancialCellSnapshot>>((lookup, cell) => {
    if (cell.cell_ref) {
      lookup[cell.cell_ref] = cell;
    }
    return lookup;
  }, {});
}

function checkDetail(check: HardGateCheck): string {
  if (check.reason) {
    return check.reason;
  }

  if (check.passed === false) {
    return "Check failed without a surfaced reason.";
  }

  return "No blocker surfaced.";
}

function buildControlPlaneSection(
  health?: ProjectControlPlaneHealth | null,
  deck?: ExportDeckSnapshot | null,
): ExportReadinessSection {
  const deckUnprocessedOutboxCount = numericCount(deck?.unprocessed_outbox_count);
  const deckPendingRetractionCount = numericCount(deck?.pending_source_retraction_count);

  if (!health) {
    const fallbackItems: ExportReadinessItem[] = [
      item(
        "control-plane-unavailable",
        "Control-plane status",
        "unknown",
        "Project outbox, source-retraction, and hard-gate status are not loaded.",
      ),
    ];

    if (deckUnprocessedOutboxCount > 0) {
      fallbackItems.push(
        item(
          "deck-unprocessed-outbox",
          "Deck outbox side effects",
          "blocked",
          `${deckUnprocessedOutboxCount} unprocessed outbox rows are exposed by the deck snapshot.`,
        ),
      );
    }

    if (deckPendingRetractionCount > 0) {
      fallbackItems.push(
        item(
          "deck-pending-source-retractions",
          "Deck source retraction cascade",
          "blocked",
          [
            `${deckPendingRetractionCount} pending source retractions`,
            "are exposed by the deck snapshot.",
          ].join(" "),
        ),
      );
    }

    return section("control-plane", "Control-plane gates", fallbackItems);
  }

  const items: ExportReadinessItem[] = [
    item(
      "outbox",
      "Outbox side effects",
      health.outbox.blocked ? "blocked" : "ready",
      health.outbox.blocked
        ? [
            `${health.outbox.unprocessed_count} unprocessed`,
            `${health.outbox.failed_count} failed outbox rows block export.`,
          ].join(" and ")
        : "No failed or unprocessed outbox rows surfaced.",
    ),
    item(
      "source-retractions",
      "Source retraction cascade",
      health.sourceRetractions.blocked ? "blocked" : "ready",
      health.sourceRetractions.blocked
        ? [
            `${health.sourceRetractions.pending_count} pending`,
            `${health.sourceRetractions.processing_count} processing`,
            `${health.sourceRetractions.failed_count} failed retraction events block export.`,
          ].join(", ")
        : "No open source retraction cascade surfaced.",
    ),
    item(
      "hard-gates",
      "Hard-gate bundle",
      health.hardGates.passed ? "ready" : "blocked",
      health.hardGates.passed
        ? `${health.hardGates.checks.length} hard-gate checks passed.`
        : `${health.hardGates.failed_checks.length} hard-gate checks block export.`,
    ),
  ];

  health.hardGates.failed_checks.forEach((check) => {
    items.push(
      item(
        `hard-gate-${check.name}`,
        check.name,
        "blocked",
        checkDetail(check),
      ),
    );
  });

  if (deckUnprocessedOutboxCount > 0) {
    items.push(
      item(
        "deck-unprocessed-outbox",
        "Deck outbox side effects",
        "blocked",
        `${deckUnprocessedOutboxCount} unprocessed outbox rows are exposed by the deck snapshot.`,
      ),
    );
  }

  if (deckPendingRetractionCount > 0) {
    items.push(
      item(
        "deck-pending-source-retractions",
        "Deck source retraction cascade",
        "blocked",
        [
          `${deckPendingRetractionCount} pending source retractions`,
          "are exposed by the deck snapshot.",
        ].join(" "),
      ),
    );
  }

  return section("control-plane", "Control-plane gates", items);
}

function buildVisualSection(deck?: ExportDeckSnapshot | null): ExportReadinessSection {
  const slides = deck?.slides || [];
  if (slides.length === 0) {
    return section("visuals", "Visual readiness", [
      item(
        "visuals-unavailable",
        "Degraded visual blockers",
        "unknown",
        "No deck slide snapshot is loaded for visual quality checks.",
      ),
    ]);
  }

  const items: ExportReadinessItem[] = [];
  slides.forEach((slide, index) => {
    if (slide.visual_quality !== "degraded") {
      return;
    }

    const id = slideId(slide, index);
    if (slide.materiality === "high" || slide.materiality === "medium") {
      items.push(
        item(
          `degraded-${id}`,
          `${id} degraded visual`,
          "blocked",
          "Degraded visuals cannot ship on high or medium materiality slides.",
        ),
      );
      return;
    }

    items.push(
      item(
        `degraded-${id}`,
        `${id} degraded visual`,
        "warning",
        "Low materiality degraded visual is surfaced as a warning for operator review.",
      ),
    );
  });

  if (items.length === 0) {
    items.push(
      item(
        "visuals-clear",
        "Degraded visual blockers",
        "ready",
        `${slides.length} slides checked; no degraded high or medium materiality visual surfaced.`,
      ),
    );
  }

  return section("visuals", "Visual readiness", items);
}

function buildSourceAppendixSection(
  deck?: ExportDeckSnapshot | null,
  exportMetadata?: ExportMetadataSnapshot | null,
): ExportReadinessSection {
  const slides = deck?.slides || [];
  const metadata = exportMetadata || deck?.export_metadata || null;
  const items: ExportReadinessItem[] = [];

  if (slides.length > 0) {
    materialSlides(slides).forEach((slide, index) => {
      const evidenceRefs = stringList(slide.content?.evidence_refs);
      if (evidenceRefs.length === 0) {
        const id = slideId(slide, index);
        items.push(
          item(
            `evidence-${id}`,
            `${id} source evidence`,
            "blocked",
            "High and medium materiality slides require active source evidence references.",
          ),
        );
      }
    });
  }

  const slideClaims = metadata?.slide_id_to_claim_refs;
  const claimSources = metadata?.claim_refs_to_source_refs;
  if (slideClaims && claimSources) {
    Object.entries(slideClaims).forEach(([slideIdKey, claimRefs]) => {
      claimRefs.forEach((claimRef) => {
        if (stringList(claimSources[claimRef]).length === 0) {
          items.push(
            item(
              `claim-source-${slideIdKey}-${claimRef}`,
              `${claimRef} source appendix mapping`,
              "blocked",
              [
                `${slideIdKey} maps to ${claimRef},`,
                "but no source reference is surfaced for that claim.",
              ].join(" "),
            ),
          );
        }
      });
    });

    if (items.length === 0) {
      items.push(
        item(
          "source-appendix-ready",
          "Source appendix evidence map",
          "ready",
          `${Object.keys(slideClaims).length} slide evidence-map entries surfaced.`,
        ),
      );
    }
  } else if (items.length === 0) {
    items.push(
      item(
        "source-appendix-unavailable",
        "Source appendix evidence map",
        "unknown",
        "Source appendix and evidence-map metadata are not exposed to this view.",
      ),
    );
  }

  return section("source-appendix", "Source appendix readiness", items);
}

function buildFinancialSection(
  deck?: ExportDeckSnapshot | null,
  exportMetadata?: ExportMetadataSnapshot | null,
): ExportReadinessSection {
  if (!deck) {
    return section("financial", "Financial reference readiness", [
      item(
        "financial-unavailable",
        "Financial reference status",
        "unknown",
        "No deck snapshot is loaded for financial reference checks.",
      ),
    ]);
  }

  const metadata = exportMetadata || deck.export_metadata || null;
  const lookup = financialCellLookup(deck, metadata);
  const items: ExportReadinessItem[] = [];

  if (
    deck.financial_validation_status !== undefined &&
    deck.financial_validation_status !== null &&
    deck.financial_validation_status !== "validated"
  ) {
    items.push(
      item(
        "financial-validation",
        "Financial validation",
        "blocked",
        "Financial calculations must pass deterministic validation before export.",
      ),
    );
  }

  const unsupportedClaims = numericCount(deck.unsupported_financial_claim_count);
  if (unsupportedClaims > 0) {
    items.push(
      item(
        "unsupported-financial-claims",
        "Unsupported financial claims",
        "blocked",
        `${unsupportedClaims} unsupported financial claims block export.`,
      ),
    );
  }

  (deck.slides || []).forEach((slide, index) => {
    const id = slideId(slide, index);
    stringList(slide.content?.financial_refs).forEach((financialRef) => {
      const cell = lookup[financialRef];
      if (!cell) {
        items.push(
          item(
            `financial-ref-missing-${id}-${financialRef}`,
            `${id} ${financialRef}`,
            "blocked",
            "Financial reference does not map to a surfaced financial cell.",
          ),
        );
        return;
      }

      const validationStatus = cell.validation_status || cell.status;
      if (validationStatus !== "validated") {
        items.push(
          item(
            `financial-ref-unvalidated-${id}-${financialRef}`,
            `${id} ${financialRef}`,
            "blocked",
            "Financial reference maps to a cell that is not validated.",
          ),
        );
      }
    });
  });

  if (items.length === 0 && Object.keys(lookup).length > 0) {
    items.push(
      item(
        "financial-ready",
        "Financial references",
        "ready",
        [
          `${Object.keys(lookup).length} surfaced financial cells are available`,
          "for reference checks.",
        ].join(" "),
      ),
    );
  } else if (items.length === 0 && deck.financial_validation_status === "validated") {
    items.push(
      item(
        "financial-validation-ready",
        "Financial validation",
        "ready",
        "Financial validation is surfaced as validated.",
      ),
    );
  } else if (items.length === 0) {
    items.push(
      item(
        "financial-not-exposed",
        "Financial reference status",
        "unknown",
        "Financial validation and reference metadata are not exposed to this view.",
      ),
    );
  }

  return section("financial", "Financial reference readiness", items);
}

function staleArtifactCheck(health?: ProjectControlPlaneHealth | null): HardGateCheck | undefined {
  return health?.hardGates.checks.find(
    (check) => check.name === "no_stale_downstream_artifacts",
  );
}

function buildStaleArtifactSection(
  health?: ProjectControlPlaneHealth | null,
  deck?: ExportDeckSnapshot | null,
): ExportReadinessSection {
  const items: ExportReadinessItem[] = [];
  const check = staleArtifactCheck(health);

  if (check?.passed === false) {
    items.push(
      item(
        "stale-artifact-hard-gate",
        "Stale downstream artifacts",
        "blocked",
        checkDetail(check),
      ),
    );
  }

  (deck?.artifacts || []).forEach((artifact, index) => {
    if (artifact.status === "stale_due_to_retreat") {
      const artifactId = artifact.id || `artifact_${index + 1}`;
      items.push(
        item(
          `stale-artifact-${artifactId}`,
          artifactId,
          "blocked",
          "Stale artifacts from a retreat cannot be exported.",
        ),
      );
    }
  });

  if (items.length === 0 && check) {
    items.push(
      item(
        "stale-artifacts-ready",
        "Stale downstream artifacts",
        "ready",
        "No stale downstream artifact blocker surfaced.",
      ),
    );
  } else if (items.length === 0) {
    items.push(
      item(
        "stale-artifacts-unavailable",
        "Stale downstream artifacts",
        "unknown",
        "Stale artifact status is not exposed to this view.",
      ),
    );
  }

  return section("stale-artifacts", "Stale artifact readiness", items);
}

export function buildExportReadinessModel({
  health,
  deck,
  exportMetadata,
  isLoading = false,
  errorMessage = null,
}: Pick<
  ExportReadinessPanelProps,
  "health" | "deck" | "exportMetadata" | "isLoading" | "errorMessage"
>): ReadinessModel {
  const sections = [
    buildControlPlaneSection(health, deck),
    buildVisualSection(deck),
    buildSourceAppendixSection(deck, exportMetadata),
    buildFinancialSection(deck, exportMetadata),
    buildStaleArtifactSection(health, deck),
  ];

  const allItems = sections.flatMap((readinessSection) => readinessSection.items);
  const blockers = allItems.filter((readinessItem) => readinessItem.status === "blocked");
  const warnings = allItems.filter((readinessItem) => readinessItem.status === "warning");
  const unknowns = allItems.filter((readinessItem) => readinessItem.status === "unknown");

  if (isLoading) {
    return {
      headline: "Checking export readiness",
      status: "unknown",
      sections,
      blockers,
      warnings,
      unknowns,
    };
  }

  if (errorMessage) {
    return {
      headline: "Export readiness unavailable",
      status: "unknown",
      sections,
      blockers,
      warnings,
      unknowns,
    };
  }

  if (blockers.length > 0) {
    return {
      headline: "Export blocked",
      status: "blocked",
      sections,
      blockers,
      warnings,
      unknowns,
    };
  }

  if (unknowns.length > 0) {
    return {
      headline: "No exposed export blockers",
      status: "unknown",
      sections,
      blockers,
      warnings,
      unknowns,
    };
  }

  if (warnings.length > 0) {
    return {
      headline: "Export ready with warnings",
      status: "warning",
      sections,
      blockers,
      warnings,
      unknowns,
    };
  }

  return {
    headline: "Export ready",
    status: "ready",
    sections,
    blockers,
    warnings,
    unknowns,
  };
}

export function ExportReadinessPanel({
  projectId,
  health = null,
  deck = null,
  exportMetadata = null,
  isLoading = false,
  errorMessage = null,
  onRefresh,
}: ExportReadinessPanelProps) {
  const model = buildExportReadinessModel({
    health,
    deck,
    exportMetadata,
    isLoading,
    errorMessage,
  });

  return (
    <section
      className="pfos-export-readiness"
      aria-labelledby="export-readiness-heading"
      aria-busy={isLoading}
    >
      <header className="pfos-export-readiness-header">
        <div>
          <p className="pfos-kicker">Export readiness</p>
          <h2 id="export-readiness-heading">{model.headline}</h2>
          <p className="pfos-project-meta">
            <span>{projectId}</span>
            <span>Read-only gate summary</span>
          </p>
        </div>

        <div className="pfos-export-readiness-actions">
          <span className={statusClass(model.status)}>
            {model.status === "blocked"
              ? "Blocked"
              : model.status === "warning"
                ? "Warnings"
                : model.status === "unknown"
                  ? "Unknown"
                  : "Ready"}
          </span>
          {onRefresh ? (
            <button type="button" onClick={onRefresh} disabled={isLoading}>
              {isLoading ? "Refreshing" : "Refresh"}
            </button>
          ) : null}
        </div>
      </header>

      {errorMessage ? (
        <p className="pfos-export-readiness-error" role="alert">
          {errorMessage}
        </p>
      ) : null}

      <dl className="pfos-export-readiness-summary">
        <div>
          <dt>Blockers</dt>
          <dd>{model.blockers.length}</dd>
        </div>
        <div>
          <dt>Warnings</dt>
          <dd>{model.warnings.length}</dd>
        </div>
        <div>
          <dt>Unknown</dt>
          <dd>{model.unknowns.length}</dd>
        </div>
      </dl>

      {model.blockers.length > 0 ? (
        <section
          className="pfos-export-readiness-blockers"
          aria-labelledby="export-blockers-heading"
        >
          <h3 id="export-blockers-heading">Export blockers</h3>
          <ul>
            {model.blockers.map((blocker) => (
              <li key={blocker.id}>
                <strong>{blocker.label}</strong>
                <span>{blocker.detail}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="pfos-empty-state">No blocking export condition is surfaced.</p>
      )}

      <div className="pfos-export-readiness-grid">
        {model.sections.map((readinessSection) => (
          <section className="pfos-health-section" key={readinessSection.id}>
            <header className="pfos-export-readiness-section-header">
              <h3>{readinessSection.title}</h3>
              <span className={statusClass(readinessSection.status)}>
                {readinessSection.status}
              </span>
            </header>
            <ul className="pfos-readiness-list">
              {readinessSection.items.map((readinessItem) => (
                <li key={readinessItem.id}>
                  <span className={statusClass(readinessItem.status)}>
                    {readinessItem.status}
                  </span>
                  <div>
                    <strong>{readinessItem.label}</strong>
                    <p>{readinessItem.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </section>
  );
}

export default ExportReadinessPanel;
