{
    "name": "POS Hotel INTC",
    "version": "19.0.1.0.2",
    "category": "Point of Sale",
    "summary": "Transfert des consommations POS vers les chambres d'hôtel",
    "depends": ["point_of_sale", "hotel"],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_payment_method_views.xml",
        "views/sale_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "POS_HOTEL_INTC/static/src/app/screens/payment_screen/payment_screen.js",
            "POS_HOTEL_INTC/static/src/app/screens/payment_screen/payment_screen.xml",
            "POS_HOTEL_INTC/static/src/app/screens/payment_screen/room_charge_popup/room_charge_popup.js",
            "POS_HOTEL_INTC/static/src/app/screens/payment_screen/room_charge_popup/room_charge_popup.xml",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}