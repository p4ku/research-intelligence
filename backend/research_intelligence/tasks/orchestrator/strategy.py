from celery import shared_task

@shared_task
def execute_dynamic_research_strategy(workspace_id, strategy_dag):
    print(f"Executing strategy for workspace {workspace_id}")
    return True
