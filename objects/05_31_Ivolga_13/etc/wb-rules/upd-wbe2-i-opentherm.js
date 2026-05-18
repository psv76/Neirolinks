/*
	Скрипт автоматизированного обновления прошивки модулей НЕВОТОН с помощью контроллера WirenBoard.
	Поддерживаются модули расширения с текущей версией прошивки >= 1.90

	thx: @alexey_gamov и всем тестировщикам!
*/

var virtual = 'nevoton-updater', git = 'https://gitlab.nevoton.ru/wirenboard-secure-ota/bcg-103-ota/-/raw/{}';

var modules = {
	'OpenTherm-Modbus-WB': {name: 'WBE2-I-OPENTHERM', file: 'opentherm_modbus_wb.enc'},
	'eBus-Modbus-WB': {name: 'WBE2-I-EBUS', file: 'ebus_modbus_wb.enc'}
}

var controls = {
	branch: {
		title: {en: 'Firmware type', ru: 'Тип целевой прошивки'}, type: 'text', value: 'master', readonly: false, order: 1,
		enum: {'master': {en: 'Release', ru: 'Основная'}, 'test': {en: 'Testing', ru: 'Тестовая'}}
	},

	slot: {
		title: {en: 'Module installed in', ru: 'Расположение модуля'}, type: 'text', value: '1', readonly: false, order: 2,
		enum: {1: {en: 'Slot 1', ru: 'Слот 1'}, 2: {en: 'Slot 2', ru: 'Слот 2'}, 3: {en: 'Slot 3', ru: 'Слот 3'}}
	},

	status: {
		title: {en: 'Current state', ru: 'Состояние'}, type: 'text', value: '-', forceDefault: true, order: 3,
		enum: {
			'Wait': {en: 'Data loading', ru: 'Загрузка данных'},
			'Network error': {en: 'Network error', ru: 'Сетевая ошибка'},
			'No module': {en: 'Module not installed', ru: 'Модуль не установлен'},
			'Module error': {en: 'Module type unknown', ru: 'Неизвестный тип модуля'},
			'Flashing data': {en: 'Flashing firmware', ru: 'Обновление прошивки'},
			'Burning data': {en: 'Installing firmware', ru: 'Установка прошивки'},
			'Burn error': {en: 'Error while burning device', ru: 'Ошибка во время записи прошивки'},
		}
	},

	module: {
		title: {en: 'Module type', ru: 'Тип модуля'}, type: 'text', value: '-', forceDefault: true, order: 4,
		enum: Object.keys(modules).reduce(function(item, type) { item[type] = { en: modules[type].name }; return item }, {})
	},

	current: {title: {en: 'Current firmware', ru: 'Установленная версия'}, type: 'text', value: '-', forceDefault: true, order: 5},
	latest: {title: {en: 'Available firmware', ru: 'Доступная версия'}, type: 'text', value: '-', forceDefault: true, order: 6},

	check: {title: {en: 'Get actual module information', ru: 'Получить информацию о модуле'}, type: 'pushbutton', order: 7},
	update: {title: {en: 'Update firmware', ru: 'Обновить прошивку'}, type: 'pushbutton', order: 8},
	force: {title: {en: 'Force burn firmware', ru: 'Прошить принудительно'}, type: 'pushbutton', order: 9},
	reset: {title: {en: 'Go back', ru: 'Назад'}, type: 'pushbutton', order: 10}
}

// Инициализируем виртуальное устройство

defineVirtualDevice(virtual, {
	title: {en: 'Nevoton · Firmware updater', ru: 'Невотон · Обновление прошивки'},
	cells: controls
});

// Создаем правило, которое отслеживает пользовательские команды

var user = defineRule(virtual, {
    whenChanged: [
		virtual + '/check', virtual + '/update', virtual + '/force',
		virtual + '/slot', virtual + '/reset'
	],
    then: function (value, device, control) {
        switch (control) {
			case 'check': case 'update':
				getDevice(virtual).removeControl('check');
				getDevice(virtual).removeControl('update');

				getControl(virtual + '/status').setValue('Wait');
				getControl(virtual + '/branch').setReadonly(true);
				getControl(virtual + '/slot').setReadonly(true);

				download_archive_and_script(control);
			break;

			case 'force':
				getControl(virtual + '/status').setValue('Burning data');
				getDevice(virtual).removeControl('force');
				burn_device();
			break;

			case 'slot': case 'reset':
				getDevice(virtual).removeControl('force');
				getDevice(virtual).removeControl('reset');

				getControl(virtual + '/status').setValue('-');
				getControl(virtual + '/branch').setReadonly(false);
				getControl(virtual + '/slot').setReadonly(false);

				getDevice(virtual).addControl('check', controls['check']);
				getDevice(virtual).addControl('update', controls['update']);
			break;

			default:
				getDevice(virtual).addControl('reset', controls['reset']);
				return;
			break;
		}

		getControl(virtual + '/current').setValue('-');
		getControl(virtual + '/latest').setValue('-');
		getControl(virtual + '/module').setValue('-');
    }
});

// Производим сброс виртуального устройства при пересохранении/перезапуске

getDevice(virtual).getControl('reset').setValue(true);

// Блок функций по запросу и обработке поступающих данных

function download_archive_and_script(command) {
	var cmd = [
		'mkdir -p /home/nevoton_gate',
		'wget -O /home/nevoton_gate/nvt_lin.tar -P /home/nevoton_gate "{}/nvt_lin.tar?ref_type=heads&inline=false"'.format(git.format(dev[virtual].branch)),
		'wget -O /home/nevoton_gate/script.sh -P /home/nevoton_gate "{}/burn.sh?ref_type=heads&inline=false"'.format(git.format(dev[virtual].branch))
	];

	runShellCommand(cmd.join(' && '), {
		captureOutput: true,
		exitCallback: function (code, output) {
			log.debug('download_archive_and_script = exit code: {}', code);

			getControl(virtual + '/module').setReadonly(true);

			if (code != 0) {
				log.debug('download_archive_and_script = error code: {}, output: {}', code , output);

				if (command == 'check') get_device_info(command, false);

				getControl(virtual + '/status').setValue('Network error');
				runRule(user);

				return;
			}

			runShellCommand('cd /home/nevoton_gate && tar --overwrite -xf nvt_lin.tar', {
				captureOutput: true,
				exitCallback: function (code, output) {
					if (code != 0) {
						log.debug('download_archive_and_script = error code: {}, output: {}', code , output);
						runRule(user);
					}
					else get_device_info(command, true);
				}
			});
		}
	});
}

function get_device_info(command, connection) {
	var types = Object.keys(modules);

    if (command == 'check' && !connection) {
		runShellCommand('test -d /home/nevoton_gate/nvt && echo "exists" || echo "does not exist"', {
			captureOutput: true,
			exitCallback: function (code, output) {
				if (code == 0 && output == 'exists') get_device_info('dummy', false);
				log.debug('get_device_info > check_for_nvt_directory = exit code: {}, output: {}', code, output);
			}
		});
	}
    else if (dev[virtual].module == '-') {
        runShellCommand('bash /home/nevoton_gate/script.sh MOD{}'.format(dev[virtual].slot), {
            captureOutput: true,
            exitCallback: function (code, output) {
                if (code == 0) {
                    var data = JSON.parse(output);

                    log.debug('get_device_info = result: {} {}', data['version'], data['name']);

                    if (types.indexOf(data['name']) !== -1) {
						getControl(virtual + '/module').setValue(data['name']);
						
                        if (command == 'check') {
							var version = (data['version'] / 100).toString();
							getControl(virtual + '/current').setValue(version);
						}

						if (connection) get_version_latest(command);
                        else getControl(virtual + '/latest').setValue('?');
                    }
					else {
						getControl(virtual + '/status').setValue('Module error');
						getControl(virtual + '/module').setValue(data['name']);
						runRule(user);
					}
                }
                else {
                    log.debug('get_device_info = error code: {}, output: {}', code, output);

					getControl(virtual + '/status').setValue('No module');
                    runRule(user);
                }
            }
        });
    }
    else if (connection && types.indexOf(data['name']) !== -1) {
		getControl(virtual + '/current').setValue('?');
		get_version_latest(command);
	}
	else {
		log.debug('get_device_info = error: "Nevaton devices are in support only - change port and try again"');

		getControl(virtual + '/status').setValue('Module error');
		getControl(virtual + '/module').setValue(Object.keys(modules)[0]);
		getControl(virtual + '/module').setReadonly(false);

		getDevice(virtual).addControl('force', controls['force']);

		runRule(user);
	}
}

function get_version_latest(command) {
    runShellCommand('wget -O /home/nevoton_gate/version.json -P /home/ot_modbus/wb "{}/version.json?ref_type=heads&inline=false"'.format(git.format(dev[virtual].branch)), {
        captureOutput: true,
        exitCallback: function (code, output) {
            log.debug('get_version_latest = exit code: {}', code);

            if (code != 0) {
                log.debug('download version files = error code: {}, output: {}', code, output);

                getControl(virtual + '/status').setValue('Network error');
                runRule(user);
            }
			else show_version_latest(command);
        }
    });
}

function show_version_latest(command) {
    runShellCommand('cat /home/nevoton_gate/version.json', {
        captureOutput: true,
        exitCallback: function (code, output) {
            if (code == 0) {
				var version = (JSON.parse(output)[dev[virtual].module] / 100).toString();

				getControl(virtual + '/latest').setValue(version);

                if (command != 'update') {
					getDevice(virtual).addControl('update', controls['update']);
					getControl(virtual + '/status').setValue('-');
                    runRule(user);
                }
				else {
					getControl(virtual + '/status').setValue('Flashing data');
					burn_device();
				}
            }
            else {
				log.debug('show_version_latest = error code: {}, output: {}', code , output);
                runRule(user);
            }
        }
    });
}

function burn_device() {
    runShellCommand('bash /home/nevoton_gate/script.sh MOD{} {}'.format(dev[virtual].slot, modules[dev[virtual].module].file), {
        captureOutput: true,
        exitCallback: function (code, output) {
            if (code == 0) {
				var version = (JSON.parse(output)['version'] / 100).toString();

				getControl(virtual + '/current').setValue(version);
				getControl(virtual + '/status').setValue('-');

				log.debug('burn_device = exit code: {}', code);
            }
            else {
				getControl(virtual + '/status').setValue('Burn error');

                log.debug('burn_device = error code: {}, output: {}', code, output);
            }

			runRule(user);
        }
    });
}