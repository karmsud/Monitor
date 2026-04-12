from backend.db import queries


def test_recent_queries_use_execution_timestamp_expression():
    expr = queries.TEMPLATE_STAGING_EXECUTION_TS

    assert expr in queries.GET_RECENT_BY_TEMPLATE_NAME
    assert expr in queries.GET_RECENT_BY_DID
    assert expr in queries.GET_RECENT_BY_SERVICER
    assert expr in queries.GET_FAILURES_IN_PERIOD
    assert expr in queries.GET_DURATION_STATS
    assert expr in queries.GET_SOURCE_PROCESS_BREAKDOWN


def test_date_range_query_uses_execution_timestamp_expression():
    expr = queries.TEMPLATE_STAGING_EXECUTION_TS

    assert expr in queries.GET_TEMPLATE_STAGING_BY_DATE_RANGE