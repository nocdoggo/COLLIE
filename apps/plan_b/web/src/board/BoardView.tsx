// The board as a pure function of one EventStateView. The live board and the recorded replay
// render this same component; it performs no requests and imports nothing from src/api.ts.

import type { ReactNode } from "react";

import { ActionHistory } from "../components/ActionHistory";
import { BoardHeader } from "../components/BoardHeader";
import type { BoardMode } from "../components/BoardHeader";
import { CandidateComparison } from "../components/CandidateComparison";
import { ChangeSummary } from "../components/ChangeSummary";
import { Authority, Constraints } from "../components/Constraints";
import { Decisions, EvidenceDrawer, Transitions } from "../components/Decisions";
import { Observations, StatusChecks } from "../components/Observations";
import { PlanComparison } from "../components/PlanComparison";
import { Budget, HoldsAndCommitments, RoleReadiness } from "../components/Resources";
import { Schedule } from "../components/Schedule";
import type { EventStateView } from "../types";

export function BoardView({
  view,
  mode,
  headerActions,
  panel,
  beforeGrid,
  showHeader = true,
}: {
  view: EventStateView;
  mode: BoardMode;
  /** The live page renders the header itself so its control deck can sit right below it. */
  showHeader?: boolean;
  /** Small controls placed in the header strip (for example, sign out). */
  headerActions?: ReactNode;
  /** The signed-in role's controls (live board only). */
  panel?: ReactNode;
  /** Content between the header and the board grid (for example, replay frame controls). */
  beforeGrid?: ReactNode;
}) {
  return (
    <div className={`board board-${mode}`}>
      {showHeader ? <BoardHeader view={view} mode={mode} actions={headerActions} /> : null}
      {beforeGrid}
      <div className="board-grid">
        <div className="col-main">
          <ChangeSummary view={view} />
          <Schedule view={view} />
          <StatusChecks view={view} mode={mode} />
          <PlanComparison view={view} />
          <CandidateComparison view={view} />
        </div>
        <div className="col-side">
          {panel}
          <Budget view={view} />
          <RoleReadiness view={view} />
          <HoldsAndCommitments view={view} />
          <Constraints view={view} />
          <Authority view={view} />
        </div>
      </div>
      <div className="board-wide">
        <Observations view={view} mode={mode} />
        <ActionHistory view={view} />
        <Decisions view={view} />
        <Transitions view={view} />
        <EvidenceDrawer view={view} />
      </div>
    </div>
  );
}
