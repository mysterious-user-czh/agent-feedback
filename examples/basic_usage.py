"""Demonstrate evidence recording; this example does not convert a document."""
from pathlib import Path
from agent_feedback import FeedbackService

service = FeedbackService(Path(__file__).parent / "demo.db")
task = service.start("generic-agent", "Convert a Word document to PDF")["task_id"]
service.event(task, "selection", {"kind": "skill", "name": "microsoft-office", "source": "observed"})
service.event(task, "tool_result", {"name": "document-converter", "status": "success"})
service.event(task, "artifact", {"name": "converted PDF", "reference": "output/report.pdf"})
service.event(task, "process_result", {"exit_code": 0})
service.event(task, "verification", {"outcome": "success", "evidence": ["PDF opened successfully; page count=3"], "source": "observed", "artifact_source": "live"})
service.label(task, "success")
print(service.report(agent="generic-agent"))
service.close()
