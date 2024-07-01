# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later


class AdminMenuBase:
    def on_enter(self):
        """
        Enter callback

        Override this to implement custom action on menu enter
        """

    def on_reenter(self):
        """
        Re-enter callback

        Override this to implement custom action on menu enter by menus tack pop.
        """

    def on_leave(self):
        """
        Leave callback

        Override this to implement custom action on menu leave
        """
