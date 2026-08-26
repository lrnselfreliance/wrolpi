import React, {useContext, useEffect, useState} from 'react';
import {Route, Routes} from 'react-router';

import {getAiCatalog, postAiSettings, postDownload} from '../api';
import {getServiceStatus, startService, stopService} from '../api/controller';
import {StatusContext} from '../contexts/contexts';
import {APIButton, humanFileSize, InfoMessage, PageContainer, TabLinks, useTitle, WROLModeMessage} from './Common';
import {SortableTable} from './SortableTable';
import {Button, Divider, Group, Header, NumberInput, Select, Table, Text, Toggle, toast} from './ui';
import {Downloaders} from './Vars';

// The Controller's name for llama-server: the compose service in docker, the systemd unit natively.
export const llmServiceName = (dockerized) => dockerized ? 'llm' : 'wrolpi-llm';

export function AiModelRow({model, onDownload}) {
    const {name, tier, size, description, downloaded, active} = model;

    return <Table.Row>
        <Table.Cell>
            <Text fw={active ? 700 : undefined}>{name}{active ? ' (active)' : ''}</Text>
            {description && <Text size='sm' c='dimmed'>{description}</Text>}
        </Table.Cell>
        <Table.Cell>{tier}</Table.Cell>
        <Table.Cell>{humanFileSize(size)}</Table.Cell>
        <Table.Cell>
            {downloaded
                ? <Button size='xs' icon='check' disabled role='save'>Downloaded</Button>
                : <APIButton size='xs' icon='download' color='violet' onClick={() => onDownload(model)}>
                    Download
                </APIButton>}
        </Table.Cell>
    </Table.Row>;
}

export function ManageAi() {
    const [catalog, setCatalog] = useState(null);
    const [serviceStatus, setServiceStatus] = useState(null);
    const [pendingSave, setPendingSave] = useState(false);
    const {status} = useContext(StatusContext);
    const serviceName = llmServiceName(status?.dockerized);

    const fetchCatalog = async () => {
        try {
            const data = await getAiCatalog();
            if (data) {
                setCatalog(data);
            }
        } catch (e) {
            console.error(e);
        }
    };

    const fetchService = async () => {
        try {
            setServiceStatus(await getServiceStatus(serviceName));
        } catch (e) {
            // The service is unknown until AI is installed; not an error worth toasting.
            setServiceStatus(null);
        }
    };

    useEffect(() => {
        fetchCatalog();
        fetchService();
        const interval = setInterval(() => {
            fetchCatalog();
            fetchService();
        }, 30000);
        return () => clearInterval(interval);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [serviceName]);

    const handleDownload = async (model) => {
        await postDownload({
            urls: [model.url],
            downloader: Downloaders.AiModel,
            destination: 'ai/models',
        });
        toast({
            type: 'success',
            title: 'Download started',
            description: 'Monitor progress on the Downloads page.',
            time: 5000,
        });
    };

    const saveSettings = async (settings) => {
        setPendingSave(true);
        try {
            await postAiSettings(settings);
            await fetchCatalog();
        } finally {
            setPendingSave(false);
        }
    };

    const handleServiceButton = async () => {
        if (serviceStatus?.status === 'running') {
            await stopService(serviceName);
        } else {
            await startService(serviceName);
        }
        await fetchService();
    };

    if (!catalog) {
        return <WROLModeMessage content='Cannot modify AI'/>;
    }

    const {models, recommended_tier, total_ram, slow_hardware, disk_usage, enabled, active_model} = catalog;
    const downloadedModels = models.filter(i => i.downloaded);

    const modelHeaders = [
        {key: 'name', text: 'Model', sortBy: i => i.name.toLowerCase()},
        {key: 'tier', text: 'Tier', sortBy: i => i.tier},
        {key: 'size', text: 'Size', sortBy: i => i.size || 0},
        {key: 'actions', text: '', sortBy: null},
    ];

    return <>
        <WROLModeMessage content='Cannot modify AI'/>

        {slow_hardware && <InfoMessage storageName='hint_ai_slow_hardware'>
            This hardware will run the assistant slowly. Answers may take minutes; the smallest
            model is recommended.
        </InfoMessage>}

        <Header as='h3'>AI Assistant</Header>
        <Group gap='lg'>
            <Toggle
                label='Enabled'
                checked={enabled === true}
                disabled={pendingSave || !active_model}
                onChange={e => saveSettings({enabled: e.target.checked})}
            />
            <Select
                label='Active Model'
                data={downloadedModels.map(i => ({value: i.name, label: i.name}))}
                value={active_model || null}
                placeholder={downloadedModels.length ? 'Select a model' : 'Download a model below'}
                disabled={pendingSave || !downloadedModels.length}
                onChange={value => value && saveSettings({active_model: value})}
            />
            <NumberInput
                label='Idle unload (minutes)'
                min={1}
                value={catalog.idle_unload_minutes}
                disabled={pendingSave}
                onChange={value => value && saveSettings({idle_unload_minutes: value})}
            />
        </Group>

        {enabled && <Group gap='xs' style={{marginTop: '1em'}}>
            <Text>Service: {serviceStatus?.status || 'unknown'}</Text>
            <APIButton
                size='xs'
                color={serviceStatus?.status === 'running' ? undefined : 'violet'}
                role={serviceStatus?.status === 'running' ? 'danger' : undefined}
                onClick={handleServiceButton}
            >
                {serviceStatus?.status === 'running' ? 'Stop' : 'Start'}
            </APIButton>
        </Group>}

        <Divider/>

        <Header as='h3'>Model Catalog</Header>
        <Text size='sm'>
            This device has {humanFileSize(total_ram)} of RAM;
            the <b>{recommended_tier}</b> tier is recommended.
            Models use {humanFileSize(disk_usage)} in <b>ai/models/</b>.
        </Text>
        <SortableTable
            tableHeaders={modelHeaders}
            data={models}
            rowFunc={(model) => <AiModelRow key={model.name} model={model} onDownload={handleDownload}/>}
            rowKey='name'
            defaultSortColumn='size'
        />

        <InfoMessage storageName='hint_ai_models'>
            <p>The AI assistant runs entirely on this WROLPi — no internet is needed after a model
                is downloaded. Download a model, select it, then enable the assistant. Monitor
                download progress on the <b>Downloads</b> page.</p>
        </InfoMessage>
    </>;
}

function ChatPlaceholder() {
    return <Text>Chat is coming soon. Configure the assistant on the Manage tab.</Text>;
}

export function AiRoute() {
    useTitle('AI');

    const links = [
        {text: 'Chat', to: '/ai', key: 'chat', end: true},
        {text: 'Manage', to: '/ai/manage', key: 'manage'},
    ];

    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' exact element={<ChatPlaceholder/>}/>
            <Route path='manage' exact element={<ManageAi/>}/>
        </Routes>
    </PageContainer>;
}
