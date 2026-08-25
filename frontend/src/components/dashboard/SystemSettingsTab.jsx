import React from 'react';
import { Col, Row } from 'antd';

import AccountSecurityCard from './system-settings/AccountSecurityCard';
import AiProviderCard from './system-settings/AiProviderCard';
import ApiKeysCard from './system-settings/ApiKeysCard';
import SystemBasicsCard from './system-settings/SystemBasicsCard';
import TelegramSettingsCard from './system-settings/TelegramSettingsCard';
import EditorialProfilesCard from './system-settings/EditorialProfilesCard';

export default function SystemSettingsTab() {
    return (
        <div style={{ padding: '0 10px' }}>
            <h3>系统配置</h3>

            <Row gutter={16} style={{ marginBottom: 20 }}>
                <Col xs={24}>
                    <SystemBasicsCard />
                </Col>
            </Row>

            <Row gutter={16}>
                <Col xs={24} md={12}>
                    <AiProviderCard />
                </Col>
                <Col xs={24} md={12}>
                    <TelegramSettingsCard />
                </Col>
            </Row>

            <Row gutter={16}>
                <Col xs={24}>
                    <EditorialProfilesCard />
                </Col>
            </Row>

            <Row gutter={16} style={{ marginBottom: 20 }}>
                <Col xs={24} lg={12}>
                    <AccountSecurityCard />
                </Col>
                <Col xs={24} lg={12}>
                    <ApiKeysCard />
                </Col>
            </Row>
        </div>
    );
}
