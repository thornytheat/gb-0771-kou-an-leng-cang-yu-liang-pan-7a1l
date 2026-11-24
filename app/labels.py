TABS = {'intake':'原件采信','registry':'槽位版本','custody':'查验占位','exposure':'门区暴露','capacity':'余量对账',
        'reservations':'收货预约','history':'批次留档','certificate':'冷库证据'}
KINDS = {'closed':'闭门','warm':'温超限','cooled':'温合格','missing_temp':'温度缺证','missing_slot':'槽位缺证','missing_door':'门态缺证'}
CODES = {'WIDTH':'列数不符','MISSING':'必填字段缺失','MOVE_FIELDS':'动作字段不符','TIME':'时间无效',
         'SIGNAL':'门信号无效','EVENT_CONFLICT':'同号日志矛盾','DUP_PACKET':'重复收件','SLOT_AMBIGUOUS':'槽位版本冲突',
         'SLOT_UNKNOWN':'缺少槽位证据','CAPACITY_EXCEEDED':'调入超出槽位容量','INVALID_LIFECYCLE':'无效入出库动作',
         'SIMULTANEOUS':'同刻动作冲突','LOT_UNKNOWN':'未知货批','TICKET_MISMATCH':'查验单不匹配','ALREADY_FROZEN':'货批已冻结',
         'FROZEN_OUT':'冻结件不得出库','DOOR_BOUNCE':'门信号抖动','DOOR_CONFLICT':'同刻门态矛盾',
         'TEMP_INVALID':'温度读数无效','TEMP_CONFLICT':'同刻温度矛盾',
         'ORDER_REQUIRED':'预约单号为空','RESERVATION_PIECES':'预约件数不符','LOT_RESERVED':'货批重复预约',
         'SLOT_UNAVAILABLE':'槽位缺有效版本','ROOM_TAKEN':'槽位余量不足','ORDER_MISMATCH':'预约单号冲突',
         'NO_RESERVATION':'预约单不存在','BAD_RESERVATION':'预约参数无效'}
STATUS = {'held':'预留','fulfilled':'实占','pending':'待协调'}
