from faststream.rabbit import ExchangeType, RabbitExchange

exchanges = {
    'core_sync_extra_data_categories': RabbitExchange(name='core_sync_extra_data_categories', type=ExchangeType.FANOUT),
    'scheduler_sync_templates': RabbitExchange(name='scheduler_sync_templates', type=ExchangeType.FANOUT),
    'scheduler_run_task': RabbitExchange(name='scheduler_run_task', type=ExchangeType.FANOUT),
}
