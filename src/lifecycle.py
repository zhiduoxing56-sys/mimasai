"""Application-wide ownership, durable phases and fail-closed delivery.

Protocol output is retained on delivery failure. This module deliberately has
no delivery-repair or material-reexecution API.
"""
import contextlib
from .mpc import require
from .storage import workflow_lease,lease,record,transition,event,burn,abort_signals

class Workflow:
    def __init__(self,sid,document,persist,claim=False):
        self.sid=sid;self.document=document;self.persist=persist;self.claim=claim;self.stage='claim'
    def phase(self,stage):
        self.stage=stage;event(self.sid,stage,status='started')
    def complete(self):
        # Persist the COMPLETE document first. If this fails, the workflow is
        # aborted and its independent journal overrides any earlier report.
        self.phase('report_commit');self.persist()
        transition(self.sid,{'running'},'completed','full delivery/publication report persisted')
        event(self.sid,'completed',status='complete',proof=dict(stopped=True))
    def __enter__(self):
        self.stack=contextlib.ExitStack()
        try:
            self.stack.enter_context(workflow_lease(self.sid))
            self.stack.enter_context(abort_signals())
            if self.claim:
                with lease(self.sid):
                    require(record(self.sid) and record(self.sid)['state']=='ready','SESSION_STATE_REJECTED')
                    transition(self.sid,{'ready'},'preparing','application owns preparation and delivery')
            self.phase('claimed');return self
        except BaseException:
            self.stack.close();raise
    def __exit__(self,kind,error,tb):
        try:
            if error is not None:
                reason=type(error).__name__+':'+str(error)
                entry=record(self.sid)
                confirmed=getattr(error,'stopped',True) and not (entry and entry['state']=='stopping')
                event(self.sid,self.stage,status='failed',reason=reason,proof=dict(stopped=confirmed))
                if entry and entry['state'] not in ('completed','cleaned'):
                    burn(self.sid,reason,stopped=confirmed)
                self.document.update(terminal_error=reason,failure_stage=self.stage,success=False)
                if not entry or entry['state'] not in ('completed','cleaned'):
                    self.document['delivery_state']='incomplete'
                try:self.persist()
                except BaseException as saving:
                    event(self.sid,'failure_report_save',status='failed',reason=type(saving).__name__+':'+str(saving))
                # No unknown/running group can be cleaned. Failed new sessions
                # follow exactly the same validated preview policy.
                if confirmed and record(self.sid) and record(self.sid)['state']=='aborted':
                    try:
                        from .retention import auto
                        self.document['retention']=auto(self.sid)
                        self.persist()
                    except BaseException as cleaning:
                        event(self.sid,'failure_retention',status='failed',reason=type(cleaning).__name__+':'+str(cleaning))
        finally:self.stack.close()
        return False
