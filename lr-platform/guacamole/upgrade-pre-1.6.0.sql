-- Apache Guacamole 1.6.0 adds the AUDIT system permission. This ALTER is
-- idempotent and is run on both existing 1.5.x databases and fresh databases.
ALTER TABLE `guacamole_system_permission`
    MODIFY `permission` enum('CREATE_CONNECTION',
                             'CREATE_CONNECTION_GROUP',
                             'CREATE_SHARING_PROFILE',
                             'CREATE_USER',
                             'CREATE_USER_GROUP',
                             'AUDIT',
                             'ADMINISTER') NOT NULL;
