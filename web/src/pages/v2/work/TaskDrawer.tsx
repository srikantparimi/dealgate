/**
 * Task drawer — the right-Sheet detail per spec §6.
 *
 * Shows title, linked record, description, owner, due date/time,
 * priority, checklist, comments, attachments, history. Actions vary by
 * the underlying task type:
 *
 * - Manually completable tasks expose Complete / Reopen.
 * - Approval + signature tasks NEVER show a generic Complete button —
 *   they show "Open workflow" so the user routes through the state
 *   machine instead.
 * - Every task exposes Reassign (server enforces the role).
 *
 * The drawer never mutates state directly; it calls the two handlers
 * the parent injects. That keeps the page-level side effects (toasts,
 * refresh) in one place.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import type { TaskInboxRow } from "../../../api/client";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { Label } from "../../../ui-v2/primitives/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../../../ui-v2/primitives/sheet";
import {
  canCheckboxComplete,
  isOverdue,
  nextActionLabel,
  overdueDays,
  statusLabel,
  statusTone,
} from "./taskDisplay";

export interface TaskDrawerProps {
  task: TaskInboxRow | null;
  now: Date;
  busy?: boolean;
  onClose: () => void;
  onComplete: (task: TaskInboxRow) => void;
  onReopen: (task: TaskInboxRow) => void;
  onReassign: (task: TaskInboxRow, newOwnerId: string) => void;
}

export function TaskDrawer({
  task,
  now,
  busy,
  onClose,
  onComplete,
  onReopen,
  onReassign,
}: TaskDrawerProps) {
  const [assignee, setAssignee] = useState("");

  const open = task !== null;
  const workflowOnly = task ? !canCheckboxComplete(task) : false;
  const overdue = task ? isOverdue(task, now) : false;
  const overdueBy = task ? overdueDays(task, now) : 0;

  function handleReassign() {
    if (!task || !assignee.trim()) return;
    onReassign(task, assignee.trim());
    setAssignee("");
  }

  return (
    <Sheet open={open} onOpenChange={(o) => (o ? undefined : onClose())}>
      <SheetContent aria-label="Task detail" className="overflow-y-auto">
        {task ? (
          <>
            <SheetHeader>
              <SheetTitle>{task.subject}</SheetTitle>
              <SheetDescription>
                Task detail. Complete + Reopen call the workflow; approval
                and signature tasks route through their own screens so a
                checkbox can never bypass a gate.
              </SheetDescription>
            </SheetHeader>

            <dl className="mt-4 grid grid-cols-1 gap-3 text-body">
              <div>
                <dt className="text-secondary text-text-secondary">Status</dt>
                <dd className="mt-1 flex items-center gap-2">
                  <StatusBadge
                    tone={statusTone(task.status)}
                    label={statusLabel(task.status)}
                  />
                  {overdue ? (
                    <StatusBadge
                      tone="danger"
                      label={`Overdue by ${overdueBy}d`}
                    />
                  ) : null}
                </dd>
              </div>
              <div>
                <dt className="text-secondary text-text-secondary">Category</dt>
                <dd className="text-text">{task.category ?? "General"}</dd>
              </div>
              <div>
                <dt className="text-secondary text-text-secondary">Owner</dt>
                <dd className="text-text tnum">
                  {task.owner_name ?? "Unassigned"}
                </dd>
              </div>
              <div>
                <dt className="text-secondary text-text-secondary">Due date</dt>
                <dd className="text-text tnum">{task.due_date ?? "No due date"}</dd>
              </div>
              <div>
                <dt className="text-secondary text-text-secondary">
                  Escalation level
                </dt>
                <dd className="text-text tnum">
                  {task.escalation_level > 0
                    ? `Level ${task.escalation_level} — routed to manager per rule`
                    : "None"}
                </dd>
              </div>
              <div>
                <dt className="text-secondary text-text-secondary">
                  Next action
                </dt>
                <dd className="text-text">{nextActionLabel(task)}</dd>
              </div>
            </dl>

            {!task.category?.startsWith("approval.") && <div className="mt-6 border-t border-divider pt-4">
              <h3 className="text-section text-text mb-3">Reassign</h3>
              <div className="flex flex-col gap-2">
                <Label htmlFor="reassign-owner">New owner (user id)</Label>
                <Input
                  id="reassign-owner"
                  value={assignee}
                  onChange={(e) => setAssignee(e.target.value)}
                  placeholder="paste user UUID"
                />
                <Button
                  variant="secondary"
                  onClick={handleReassign}
                  disabled={busy || !assignee.trim()}
                >
                  Reassign task
                </Button>
              </div>
            </div>}

            <div className="mt-6 flex flex-col gap-2 border-t border-divider pt-4">
              {task.record_url && <Button variant="secondary" asChild><Link to={task.record_url}>Open agreement</Link></Button>}
              {workflowOnly ? (
                <>
                  <p className="text-body text-text-secondary">
                    This is a{" "}
                    <span className="text-text font-medium">
                      {task.category ?? "workflow"}
                    </span>{" "}
                    task. It cannot be completed with a checkbox — open
                    the underlying workflow instead.
                  </p>
                  <Button variant="primary" asChild>
                    <Link
                      to={
                        task.workflow_href ?? (task.category === "signature"
                          ? "/handoffs"
                          : "/sows")
                      }
                    >
                      Open workflow
                    </Link>
                  </Button>
                </>
              ) : task.status === "done" ? (
                <Button
                  variant="secondary"
                  onClick={() => onReopen(task)}
                  disabled={busy}
                >
                  Reopen task
                </Button>
              ) : (
                <Button
                  variant="primary"
                  onClick={() => onComplete(task)}
                  disabled={busy}
                >
                  Complete task
                </Button>
              )}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
