<script lang="ts">
	import { onMount } from 'svelte';
	import '@babylonjs/core/Lights/Shadows/shadowGeneratorSceneComponent';
	import { Engine } from '@babylonjs/core/Engines/engine';
	import { Scene } from '@babylonjs/core/scene';
	import { Vector3 } from '@babylonjs/core/Maths/math.vector';
	import { Color3, Color4 } from '@babylonjs/core/Maths/math.color';

	import { ArcRotateCamera } from '@babylonjs/core/Cameras/arcRotateCamera';
	import { HemisphericLight } from '@babylonjs/core/Lights/hemisphericLight';
	import { DirectionalLight } from '@babylonjs/core/Lights/directionalLight';
	import { ShadowGenerator } from '@babylonjs/core/Lights/Shadows/shadowGenerator';

	import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder';
	import type { Mesh } from '@babylonjs/core/Meshes/mesh';
	import { TransformNode } from '@babylonjs/core/Meshes/transformNode';

	import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial';

	import '@babylonjs/core/Rendering/edgesRenderer';

	type AssetType = 'screw' | 'dowel' | 'panel' | 'leg' | 'tool';

	type CommandName = 'pick' | 'move' | 'align' | 'insert' | 'place' | 'rotate' | 'release';

	type Vec3Like = {
		x: number;
		y: number;
		z: number;
	};

	type AssetInstance = {
		id: string;
		type: AssetType;
		label: string;
		position: Vec3Like;
		rotation?: Vec3Like;
		options?: Record<string, number | string | boolean>;
		mountPoints?: Record<string, Vec3Like>;
	};

	type AssemblyCommand = {
		step: number;
		order: number;
		command: CommandName;
		objectId: string;
		from: string;
		to: string;
		description: string;
		sourceObjectId?: string;
		repetitionIndex?: number;
		repetitionCount?: number;
	};

	type ParsedAssemblyProgram = {
		steps: number[];
		repetitions: Record<number, number>;
		commands: AssemblyCommand[];
	};

	type FurnitureModel = {
		title: string;
		description: string;
		object_family: string;
		asset_vocabulary: AssetType[];
		assets: AssetInstance[];
		commands: AssemblyCommand[];
	};

	type SceneObject = {
		id: string;
		type: AssetType;
		label: string;
		root: TransformNode;
		meshes: Mesh[];
		mountPoints: Record<string, Vector3>;
		graspPoint: Vector3;
	};

	type InitialTransform = {
		position: Vector3;
		rotation: Vector3;
	};

	const DEFAULT_ASP_INPUT = `step(6).
repetition(6,4).
robot_command(6,1,pick,screw_10046802,table,none,pick_up_one_of_the_4_screws_part_10046802).
robot_command(6,2,move,screw_10046802,table,screw_hole,move_the_screw_towards_the_pre_drilled_hole_on_the_frame).
robot_command(6,3,align,screw_10046802,none,screw_hole,align_the_screw_with_the_hole_on_the_frame).
robot_command(6,4,insert,screw_10046802,none,screw_hole,insert_the_screw_into_the_hole_on_the_frame_repeating_this_action_4_times).
robot_command(6,5,rotate,screw_10046802,none,none,rotate_the_screw_to_tighten_it_using_a_screwdriver).
robot_command(6,6,release,screw_10046802,none,none,release_the_screw_after_it_is_fully_tightened).`;

	const SUPPORTED_COMMANDS: CommandName[] = [
		'move',
		'pick',
		'align',
		'insert',
		'place',
		'rotate',
		'release'
	];

	const STABLE_LOCATIONS = ['none', 'start_pos', 'table'];
	const API_BASE_URL = 'http://localhost:8000';
	const DEFAULT_PAGE_ID = '0';

	const DEFAULT_PROGRAM: ParsedAssemblyProgram = parseAssemblyProgram(DEFAULT_ASP_INPUT);
	const DEFAULT_MODEL: FurnitureModel = buildModelFromAspProgram(DEFAULT_PROGRAM);

	let canvas: HTMLCanvasElement;

	let engine: Engine | null = null;
	let scene: Scene | null = null;
	let shadowGenerator: ShadowGenerator | null = null;

	let aspInput = DEFAULT_ASP_INPUT;
	let parseError = '';

	let selectedPdfFile: File | null = null;
	let uploadedPdfName = '';
	let sessionId = '';
	let pageId = DEFAULT_PAGE_ID;
	let apiStatusText = 'Upload a furniture assembly manual PDF to generate the 3D sequence.';
	let apiError = '';
	let isUploadingPdf = false;
	let isLoadingPage = false;

	let currentProgram: ParsedAssemblyProgram = DEFAULT_PROGRAM;
	let currentModel: FurnitureModel = DEFAULT_MODEL;
	let commands: AssemblyCommand[] = DEFAULT_MODEL.commands;
	let parsedCommands: AssemblyCommand[] = DEFAULT_MODEL.commands;
	let parsedSteps: number[] = DEFAULT_PROGRAM.steps;
	let parsedRepetitions: Record<number, number> = DEFAULT_PROGRAM.repetitions;

	let currentCommandIndex = -1;
	let isPlaying = false;
	let statusText = 'Ready';

	let gripperRoot: TransformNode | null = null;
	let gripperLeft: Mesh | null = null;
	let gripperRight: Mesh | null = null;
	let heldObjectId: string | null = null;

	const objects: Record<string, SceneObject> = {};
	const initialTransforms: Record<string, InitialTransform> = {};
	let dynamicRoots: TransformNode[] = [];

	function v3(value: Vec3Like | undefined, fallback = new Vector3(0, 0, 0)) {
		if (!value) return fallback.clone();
		return new Vector3(value.x, value.y, value.z);
	}

	function optionNumber(
		options: Record<string, number | string | boolean> | undefined,
		key: string,
		fallback: number
	) {
		const value = options?.[key];
		return typeof value === 'number' ? value : fallback;
	}

	function sleep(ms: number) {
		return new Promise<void>((resolve) => {
			window.setTimeout(resolve, ms);
		});
	}

	function easeInOut(t: number) {
		return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
	}

	function stripLineComment(line: string) {
		let inQuotes = false;
		let result = '';

		for (let i = 0; i < line.length; i += 1) {
			const char = line[i];

			if (char === '"') {
				inQuotes = !inQuotes;
				result += char;
				continue;
			}

			if (char === '%' && !inQuotes) {
				break;
			}

			result += char;
		}

		return result.trim();
	}

	function splitAspArguments(input: string) {
		const result: string[] = [];
		let current = '';
		let inQuotes = false;

		for (let i = 0; i < input.length; i += 1) {
			const char = input[i];

			if (char === '"') {
				inQuotes = !inQuotes;
				current += char;
				continue;
			}

			if (char === ',' && !inQuotes) {
				result.push(current.trim());
				current = '';
				continue;
			}

			current += char;
		}

		if (current.trim().length > 0) {
			result.push(current.trim());
		}

		return result;
	}

	function stripQuotes(value: string) {
		const trimmed = value.trim();

		if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
			return trimmed.slice(1, -1);
		}

		return trimmed;
	}

	function humanizeDescription(value: string) {
		const text = stripQuotes(value)
			.replaceAll('_', ' ')
			.replace(/\s+/g, ' ')
			.trim();

		if (!text) return '';
		return text.charAt(0).toUpperCase() + text.slice(1);
	}

	function parseInteger(value: string, fieldName: string, line: string) {
		const parsed = Number(value.trim());

		if (!Number.isInteger(parsed)) {
			throw new Error(`${fieldName} deve essere un numero intero. Riga: ${line}`);
		}

		return parsed;
	}

	function parseCommandName(value: string): CommandName {
		const command = value.trim() as CommandName;

		if (!SUPPORTED_COMMANDS.includes(command)) {
			throw new Error(`Comando non supportato: ${value}`);
		}

		return command;
	}

	function sortCommands(commandList: AssemblyCommand[]) {
		return [...commandList].sort((a, b) => {
			if (a.step !== b.step) return a.step - b.step;

			const aRepetition = a.repetitionIndex ?? 1;
			const bRepetition = b.repetitionIndex ?? 1;

			if (aRepetition !== bRepetition) return aRepetition - bRepetition;
			return a.order - b.order;
		});
	}

	function isStableLocation(location: string) {
		return STABLE_LOCATIONS.includes(location);
	}

	function isMountLocation(location: string) {
		if (!location || isStableLocation(location)) return false;
		return location.startsWith('hole_') || location.includes('hole');
	}

	function getRepeatedObjectId(objectId: string, repetitionIndex: number, repetitionCount: number) {
		if (repetitionCount <= 1) return objectId;
		return `${objectId}_${repetitionIndex}`;
	}

	function getRepeatedLocation(
		location: string,
		originalObjectId: string,
		repeatedObjectId: string,
		repetitionIndex: number,
		repetitionCount: number
	) {
		if (repetitionCount <= 1) return location;
		if (location === originalObjectId) return repeatedObjectId;
		if (isStableLocation(location)) return location;
		if (!isMountLocation(location)) return location;

		if (/^hole_\d+$/.test(location)) {
			return `hole_${repetitionIndex}`;
		}

		if (new RegExp(`_${repetitionIndex}$`).test(location)) {
			return location;
		}

		return `${location}_${repetitionIndex}`;
	}

	function expandRepeatedCommands(
		commandList: AssemblyCommand[],
		repetitions: Record<number, number>
	) {
		const expanded: AssemblyCommand[] = [];

		for (const command of sortCommands(commandList)) {
			const repetitionCount = repetitions[command.step] ?? 1;

			if (repetitionCount < 1) {
				throw new Error(`La ripetizione dello step ${command.step} deve essere almeno 1.`);
			}

			for (let repetitionIndex = 1; repetitionIndex <= repetitionCount; repetitionIndex += 1) {
				const repeatedObjectId = getRepeatedObjectId(
					command.objectId,
					repetitionIndex,
					repetitionCount
				);

				expanded.push({
					...command,
					objectId: repeatedObjectId,
					from: getRepeatedLocation(
						command.from,
						command.objectId,
						repeatedObjectId,
						repetitionIndex,
						repetitionCount
					),
					to: getRepeatedLocation(
						command.to,
						command.objectId,
						repeatedObjectId,
						repetitionIndex,
						repetitionCount
					),
					sourceObjectId: command.objectId,
					repetitionIndex,
					repetitionCount
				});
			}
		}

		return sortCommands(expanded);
	}

	function parseRobotCommandFact(line: string): AssemblyCommand {
		const match = line.match(/^robot_command\s*\((.*)\)\s*\.?$/);

		if (!match) {
			throw new Error(`Riga robot_command non valida: ${line}`);
		}

		const args = splitAspArguments(match[1]);

		if (args.length !== 7) {
			throw new Error(`robot_command richiede 7 argomenti. Riga: ${line}`);
		}

		const step = parseInteger(args[0], 'step', line);
		const order = parseInteger(args[1], 'order', line);
		const command = parseCommandName(args[2]);
		const objectId = args[3].trim();
		const from = args[4].trim();
		const to = args[5].trim();
		const description = humanizeDescription(args[6]);

		if (!objectId) {
			throw new Error(`objectId mancante. Riga: ${line}`);
		}

		return {
			step,
			order,
			command,
			objectId,
			from,
			to,
			description
		};
	}

	function parseAssemblyProgram(input: string): ParsedAssemblyProgram {
		const declaredSteps = new Set<number>();
		const repetitions: Record<number, number> = {};
		const rawCommands: AssemblyCommand[] = [];

		const lines = input
			.split('\n')
			.map((line) => stripLineComment(line))
			.filter((line) => line.length > 0);

		for (const line of lines) {
			const stepMatch = line.match(/^step\s*\((.*)\)\s*\.?$/);

			if (stepMatch) {
				const args = splitAspArguments(stepMatch[1]);

				if (args.length !== 1) {
					throw new Error(`step richiede 1 argomento. Riga: ${line}`);
				}

				declaredSteps.add(parseInteger(args[0], 'step', line));
				continue;
			}

			const repetitionMatch = line.match(/^repetition\s*\((.*)\)\s*\.?$/);

			if (repetitionMatch) {
				const args = splitAspArguments(repetitionMatch[1]);

				if (args.length !== 2) {
					throw new Error(`repetition richiede 2 argomenti. Riga: ${line}`);
				}

				const step = parseInteger(args[0], 'step', line);
				const count = parseInteger(args[1], 'repetition count', line);

				if (count < 1) {
					throw new Error(`La ripetizione dello step ${step} deve essere almeno 1.`);
				}

				repetitions[step] = count;
				declaredSteps.add(step);
				continue;
			}

			if (line.startsWith('robot_command')) {
				const command = parseRobotCommandFact(line);
				rawCommands.push(command);
				declaredSteps.add(command.step);
				continue;
			}

			throw new Error(`Fatto non supportato: ${line}`);
		}

		if (rawCommands.length === 0) {
			throw new Error('Nessun robot_command trovato.');
		}

		const steps = [...declaredSteps].sort((a, b) => a - b);
		const commands = expandRepeatedCommands(rawCommands, repetitions);

		return {
			steps,
			repetitions,
			commands
		};
	}

	function inferAssetType(objectId: string): AssetType {
		const normalized = objectId.toLowerCase();

		if (normalized.startsWith('screw') || normalized.includes('screw')) return 'screw';
		if (normalized.startsWith('peg') || normalized.includes('dowel') || normalized.includes('pin')) {
			return 'dowel';
		}
		if (normalized.startsWith('tool') || normalized.includes('screwdriver')) return 'tool';
		if (normalized.startsWith('leg')) return 'leg';
		return 'dowel';
	}

	function buildObjectLabel(objectId: string, type: AssetType) {
		const normalized = objectId.replaceAll('_', ' ');

		if (type === 'screw') return `Screw ${normalized}`;
		if (type === 'dowel') return `Peg ${normalized}`;
		if (type === 'tool') return `Tool ${normalized}`;
		if (type === 'panel') return `Panel ${normalized}`;
		if (type === 'leg') return `Leg ${normalized}`;

		return normalized;
	}

	function buildObjectOptions(type: AssetType): Record<string, number | string | boolean> {
		if (type === 'screw') {
			return {
				headDiameter: 0.22,
				headHeight: 0.12,
				shaftDiameter: 0.075,
				shaftLength: 0.62,
				tipHeight: 0.18
			};
		}

		if (type === 'dowel') {
			return {
				length: 0.76,
				diameter: 0.16
			};
		}

		if (type === 'tool') {
			return {
				width: 0.34,
				height: 0.22,
				depth: 0.82
			};
		}

		return {};
	}

	function extractTrailingIndex(value: string) {
		const match = value.match(/_(\d+)$/);
		if (!match) return null;
		return Number(match[1]);
	}

	function mountPositionForIndex(index: number): Vec3Like {
		const defaultPositions: Vec3Like[] = [
			{ x: -1.15, y: 0.155, z: -0.75 },
			{ x: 1.15, y: 0.155, z: -0.75 },
			{ x: -1.15, y: 0.155, z: 0.75 },
			{ x: 1.15, y: 0.155, z: 0.75 }
		];

		if (index >= 1 && index <= defaultPositions.length) {
			return defaultPositions[index - 1];
		}

		const zeroBased = index - 1;
		const columns = 4;
		const col = zeroBased % columns;
		const row = Math.floor(zeroBased / columns);
		const x = -1.35 + col * 0.9;
		const z = -0.95 + row * 0.62;

		return { x, y: 0.155, z };
	}

	function buildMountPointsFromCommands(commandList: AssemblyCommand[]) {
		const mountNames: string[] = [];
		const objectIds = new Set(commandList.map((command) => command.objectId));

		for (const command of commandList) {
			for (const location of [command.from, command.to]) {
				if (!isMountLocation(location)) continue;
				if (objectIds.has(location)) continue;
				if (!mountNames.includes(location)) mountNames.push(location);
			}
		}

		if (mountNames.length === 0) {
			mountNames.push('hole_1', 'hole_2', 'hole_3', 'hole_4');
		}

		mountNames.sort((a, b) => {
			const aIndex = extractTrailingIndex(a) ?? Number.MAX_SAFE_INTEGER;
			const bIndex = extractTrailingIndex(b) ?? Number.MAX_SAFE_INTEGER;

			if (aIndex !== bIndex) return aIndex - bIndex;
			return a.localeCompare(b);
		});

		const mountPoints: Record<string, Vec3Like> = {};

		mountNames.forEach((mountName, index) => {
			const trailingIndex = extractTrailingIndex(mountName);
			mountPoints[mountName] = mountPositionForIndex(trailingIndex ?? index + 1);
		});

		return mountPoints;
	}

	function buildModelFromAspProgram(program: ParsedAssemblyProgram): FurnitureModel {
		const objectIds: string[] = [];

		for (const command of program.commands) {
			if (!objectIds.includes(command.objectId)) {
				objectIds.push(command.objectId);
			}
		}

		const tableStartZ = -1.15;
		const tableSpacing = 0.52;
		const mountPoints = buildMountPointsFromCommands(program.commands);

		const assets: AssetInstance[] = [
			{
				id: 'assembly_panel',
				type: 'panel',
				label: 'Assembly panel',
				position: { x: 0, y: 1.3, z: 0 },
				options: {
					width: 3.4,
					height: 0.26,
					depth: 2.35
				},
				mountPoints
			}
		];

		objectIds.forEach((objectId, index) => {
			const type = inferAssetType(objectId);
			const row = Math.floor(index / 6);
			const col = index % 6;

			assets.push({
				id: objectId,
				type,
				label: buildObjectLabel(objectId, type),
				position: {
					x: -4.1 - row * 0.45,
					y: 0.7,
					z: tableStartZ + col * tableSpacing
				},
				rotation: type === 'tool' ? { x: 0, y: 0.35, z: 0 } : undefined,
				options: buildObjectOptions(type)
			});
		});

		return {
			title: 'Robot assembly sequence',
			description:
				'Procedural Babylon.js scene generated from ASP-like step, repetition and robot_command facts.',
			object_family: 'assembly',
			asset_vocabulary: ['screw', 'dowel', 'panel', 'leg', 'tool'],
			assets,
			commands: program.commands
		};
	}

	function createMaterial(
		name: string,
		diffuse: Color3,
		specular: Color3,
		emissive = new Color3(0, 0, 0)
	) {
		if (!scene) throw new Error('Scene not initialized');

		const material = new StandardMaterial(name, scene);
		material.diffuseColor = diffuse;
		material.specularColor = specular;
		material.emissiveColor = emissive;

		return material;
	}

	function makeEdges(mesh: Mesh) {
		mesh.enableEdgesRendering();
		mesh.edgesWidth = 1.2;
		mesh.edgesColor = new Color4(0.02, 0.025, 0.035, 0.85);
	}

	function addShadow(mesh: Mesh) {
		mesh.receiveShadows = true;
		shadowGenerator?.addShadowCaster(mesh, true);
	}

	function registerObject(object: SceneObject) {
		objects[object.id] = object;

		initialTransforms[object.id] = {
			position: object.root.position.clone(),
			rotation: object.root.rotation.clone()
		};

		dynamicRoots.push(object.root);

		for (const mesh of object.meshes) {
			makeEdges(mesh);
			addShadow(mesh);
		}
	}

	function clearDynamicScene() {
		for (const root of dynamicRoots) {
			root.dispose();
		}

		dynamicRoots = [];

		for (const key of Object.keys(objects)) {
			delete objects[key];
		}

		for (const key of Object.keys(initialTransforms)) {
			delete initialTransforms[key];
		}

		gripperRoot = null;
		gripperLeft = null;
		gripperRight = null;
		heldObjectId = null;
		currentCommandIndex = -1;
		statusText = 'Ready';
	}

	function getObject(id: string) {
		const object = objects[id];

		if (!object) {
			throw new Error(`Scene object not found: ${id}`);
		}

		return object;
	}

	function getMountWorldPosition(targetId: string, mountName: string) {
		const target = getObject(targetId);
		const mount = target.mountPoints[mountName];

		if (!mount) {
			throw new Error(`Mount point not found: ${targetId}.${mountName}`);
		}

		return target.root.position.add(mount);
	}

	function getLocationWorldPosition(location: string, objectId?: string) {
		if (location === 'none') {
			if (objectId && objects[objectId]) {
				return objects[objectId].root.position.clone();
			}

			return new Vector3(0, 0, 0);
		}

		if (location === 'start_pos') {
			return new Vector3(-4.25, 2.25, 0);
		}

		if (location === 'table') {
			if (objectId && objects[objectId]) {
				return objects[objectId].root.position.clone();
			}

			return new Vector3(-4.1, 0.7, 0);
		}

		if (objects['assembly_panel']?.mountPoints[location]) {
			return getMountWorldPosition('assembly_panel', location);
		}

		if (objects[location]) {
			return objects[location].root.position.clone();
		}

		throw new Error(`Location non supportata: ${location}`);
	}

	function getCommandDestination(command: AssemblyCommand) {
		if (command.to && command.to !== 'none') return command.to;
		if (command.from && command.from !== 'none') return command.from;
		return 'none';
	}

	function setObjectHighlighted(objectId: string | null) {
		for (const object of Object.values(objects)) {
			for (const mesh of object.meshes) {
				const material = mesh.material as StandardMaterial | null;

				if (!material) continue;

				if (object.id === objectId) {
					material.emissiveColor = new Color3(0.22, 0.18, 0.06);
				} else {
					material.emissiveColor = new Color3(0, 0, 0);
				}
			}
		}
	}

	function animateNodeTo(node: TransformNode, target: Vector3, duration = 900) {
		return new Promise<void>((resolve) => {
			const from = node.position.clone();
			const startedAt = performance.now();

			function frameAnimation(now: number) {
				const elapsed = now - startedAt;
				const t = Math.min(elapsed / duration, 1);
				const eased = easeInOut(t);

				node.position = Vector3.Lerp(from, target, eased);

				if (t < 1) {
					requestAnimationFrame(frameAnimation);
				} else {
					node.position = target.clone();
					resolve();
				}
			}

			requestAnimationFrame(frameAnimation);
		});
	}

	function animateRotationY(node: TransformNode, delta: number, duration = 900) {
		return new Promise<void>((resolve) => {
			const from = node.rotation.y;
			const target = from + delta;
			const startedAt = performance.now();

			function frameAnimation(now: number) {
				const elapsed = now - startedAt;
				const t = Math.min(elapsed / duration, 1);
				const eased = easeInOut(t);

				node.rotation.y = from + (target - from) * eased;

				if (t < 1) {
					requestAnimationFrame(frameAnimation);
				} else {
					node.rotation.y = target;
					resolve();
				}
			}

			requestAnimationFrame(frameAnimation);
		});
	}

	function animateGripperOpen(open = true, duration = 350) {
		if (!gripperLeft || !gripperRight) return Promise.resolve();

		const leftTarget = open ? -0.25 : -0.105;
		const rightTarget = open ? 0.25 : 0.105;

		return new Promise<void>((resolve) => {
			const leftFrom = gripperLeft!.position.z;
			const rightFrom = gripperRight!.position.z;
			const startedAt = performance.now();

			function frameAnimation(now: number) {
				const elapsed = now - startedAt;
				const t = Math.min(elapsed / duration, 1);
				const eased = easeInOut(t);

				gripperLeft!.position.z = leftFrom + (leftTarget - leftFrom) * eased;
				gripperRight!.position.z = rightFrom + (rightTarget - rightFrom) * eased;

				if (t < 1) {
					requestAnimationFrame(frameAnimation);
				} else {
					gripperLeft!.position.z = leftTarget;
					gripperRight!.position.z = rightTarget;
					resolve();
				}
			}

			requestAnimationFrame(frameAnimation);
		});
	}

	function getGripperPositionForObject(object: SceneObject) {
		return object.root.position.add(object.graspPoint).add(new Vector3(0, 0.34, 0));
	}

	async function moveGripperTo(position: Vector3, duration = 700) {
		if (!gripperRoot) return;
		await animateNodeTo(gripperRoot, position, duration);
	}

	function setActiveCommand(index: number) {
		currentCommandIndex = index;

		const command = commands[index];

		const repetitionText =
			command.repetitionCount && command.repetitionCount > 1
				? ` — repetition ${command.repetitionIndex}/${command.repetitionCount}`
				: '';

		statusText = `Step ${command.step}${repetitionText} — ${command.order}. ${command.command.toUpperCase()} — ${command.description}`;
		setObjectHighlighted(command.objectId);
	}

	function resetScene() {
		currentCommandIndex = -1;
		isPlaying = false;
		heldObjectId = null;
		statusText = 'Ready';
		setObjectHighlighted(null);

		for (const [id, transform] of Object.entries(initialTransforms)) {
			const object = objects[id];

			if (!object) continue;

			object.root.position = transform.position.clone();
			object.root.rotation = transform.rotation.clone();
		}

		if (gripperRoot) {
			gripperRoot.position = new Vector3(-4.25, 2.25, 0);
			gripperRoot.rotation = new Vector3(0, 0, 0);
		}

		if (gripperLeft && gripperRight) {
			gripperLeft.position.z = -0.25;
			gripperRight.position.z = 0.25;
		}
	}

	async function executeMove(command: AssemblyCommand) {
		const object = getObject(command.objectId);
		const destination = getCommandDestination(command);

		if (heldObjectId === command.objectId) {
			const target = getLocationWorldPosition(destination, command.objectId);
			const objectTarget = destination.startsWith('hole_')
				? target.add(new Vector3(0, 0.95, 0))
				: target;

			const gripperTarget = objectTarget.add(object.graspPoint).add(new Vector3(0, 0.34, 0));

			await Promise.all([
				animateNodeTo(object.root, objectTarget, 1000),
				gripperRoot ? animateNodeTo(gripperRoot, gripperTarget, 1000) : Promise.resolve()
			]);

			return;
		}

		if (destination === 'table') {
			await moveGripperTo(getGripperPositionForObject(object), 650);
			return;
		}

		const target = getLocationWorldPosition(destination, command.objectId).add(new Vector3(0, 1.15, 0));
		await moveGripperTo(target, 650);
	}

	async function executePick(command: AssemblyCommand) {
		const object = getObject(command.objectId);

		await animateGripperOpen(true);
		await moveGripperTo(getGripperPositionForObject(object), 650);
		await animateGripperOpen(false);
		await sleep(150);

		heldObjectId = command.objectId;

		await Promise.all([
			animateNodeTo(object.root, object.root.position.add(new Vector3(0, 0.55, 0)), 700),
			gripperRoot
				? animateNodeTo(gripperRoot, gripperRoot.position.add(new Vector3(0, 0.55, 0)), 700)
				: Promise.resolve()
		]);
	}

	async function executeAlign(command: AssemblyCommand) {
		const object = getObject(command.objectId);
		const destination = getCommandDestination(command);
		const target = getLocationWorldPosition(destination, command.objectId);
		const objectTarget = target.add(new Vector3(0, 0.82, 0));
		const gripperTarget = objectTarget.add(object.graspPoint).add(new Vector3(0, 0.34, 0));

		if (heldObjectId === command.objectId) {
			await Promise.all([
				animateNodeTo(object.root, objectTarget, 850),
				gripperRoot ? animateNodeTo(gripperRoot, gripperTarget, 850) : Promise.resolve()
			]);
		} else {
			await moveGripperTo(gripperTarget, 850);
		}
	}

	async function executeInsert(command: AssemblyCommand) {
		const object = getObject(command.objectId);
		const destination = getCommandDestination(command);
		const target = getLocationWorldPosition(destination, command.objectId);
		const insertedPosition = target.add(new Vector3(0, 0.27, 0));
		const gripperTarget = insertedPosition.add(object.graspPoint).add(new Vector3(0, 0.34, 0));

		await Promise.all([
			animateNodeTo(object.root, insertedPosition, 900),
			gripperRoot ? animateNodeTo(gripperRoot, gripperTarget, 900) : Promise.resolve()
		]);
	}

	async function executePlace(command: AssemblyCommand) {
		const object = getObject(command.objectId);
		const destination = getCommandDestination(command);
		const target = getLocationWorldPosition(destination, command.objectId);
		const placedPosition = target.add(new Vector3(0, 0.42, 0));
		const gripperTarget = placedPosition.add(object.graspPoint).add(new Vector3(0, 0.34, 0));

		await Promise.all([
			animateNodeTo(object.root, placedPosition, 850),
			gripperRoot ? animateNodeTo(gripperRoot, gripperTarget, 850) : Promise.resolve()
		]);
	}

	async function executeRotate(command: AssemblyCommand) {
		const object = getObject(command.objectId);

		await animateRotationY(object.root, Math.PI * 4, 1100);
		await sleep(150);
	}

	async function executeRelease(command: AssemblyCommand) {
		const object = getObject(command.objectId);

		await animateGripperOpen(true);
		await sleep(150);

		heldObjectId = null;

		if (gripperRoot) {
			await animateNodeTo(gripperRoot, object.root.position.add(new Vector3(0, 1.35, 0)), 600);
		}
	}

	async function playCommand(index: number) {
		const command = commands[index];

		setActiveCommand(index);

		if (command.command === 'move') await executeMove(command);
		if (command.command === 'pick') await executePick(command);
		if (command.command === 'align') await executeAlign(command);
		if (command.command === 'insert') await executeInsert(command);
		if (command.command === 'place') await executePlace(command);
		if (command.command === 'rotate') await executeRotate(command);
		if (command.command === 'release') await executeRelease(command);
	}

	async function playAll() {
		if (isPlaying) return;

		resetScene();
		isPlaying = true;

		for (let i = 0; i < commands.length; i += 1) {
			if (!isPlaying) break;
			await playCommand(i);
			await sleep(150);
		}

		isPlaying = false;
		heldObjectId = null;
		statusText = 'Sequence completed';
		setObjectHighlighted(null);
	}

	async function playSingle(index: number) {
		if (isPlaying) return;

		resetScene();
		isPlaying = true;

		for (let i = 0; i <= index; i += 1) {
			await playCommand(i);
			await sleep(110);
		}

		isPlaying = false;
	}

	function createPanel(asset: AssetInstance, sceneRef: Scene) {
		const root = new TransformNode(asset.id, sceneRef);
		root.position = v3(asset.position);
		root.rotation = v3(asset.rotation);

		const width = optionNumber(asset.options, 'width', 3.2);
		const height = optionNumber(asset.options, 'height', 0.25);
		const depth = optionNumber(asset.options, 'depth', 2.1);

		const wood = createMaterial(
			`${asset.id}-wood-material`,
			new Color3(0.62, 0.39, 0.19),
			new Color3(0.18, 0.12, 0.08)
		);

		const dark = createMaterial(
			`${asset.id}-hole-material`,
			new Color3(0.025, 0.023, 0.021),
			new Color3(0.01, 0.01, 0.01)
		);

		const panel = MeshBuilder.CreateBox(
			`${asset.id}-body`,
			{
				width,
				height,
				depth
			},
			sceneRef
		);
		panel.parent = root;
		panel.material = wood;

		const mountPoints: Record<string, Vector3> = {};

		if (asset.mountPoints) {
			for (const [key, value] of Object.entries(asset.mountPoints)) {
				mountPoints[key] = v3(value);
			}
		}

		const meshes: Mesh[] = [panel];

		for (const [mountName, mountPosition] of Object.entries(mountPoints)) {
			const hole = MeshBuilder.CreateCylinder(
				`${asset.id}-${mountName}`,
				{
					diameter: 0.18,
					height: 0.02,
					tessellation: 48
				},
				sceneRef
			);

			hole.parent = root;
			hole.position = mountPosition.clone();
			hole.material = dark;
			meshes.push(hole);
		}

		registerObject({
			id: asset.id,
			type: 'panel',
			label: asset.label,
			root,
			meshes,
			mountPoints,
			graspPoint: new Vector3(0, 0.4, 0)
		});
	}

	function createLeg(asset: AssetInstance, sceneRef: Scene) {
		const root = new TransformNode(asset.id, sceneRef);
		root.position = v3(asset.position);
		root.rotation = v3(asset.rotation);

		const height = optionNumber(asset.options, 'height', 1.25);
		const diameterTop = optionNumber(asset.options, 'diameterTop', 0.22);
		const diameterBottom = optionNumber(asset.options, 'diameterBottom', 0.3);

		const wood = createMaterial(
			`${asset.id}-wood-material`,
			new Color3(0.5, 0.3, 0.14),
			new Color3(0.16, 0.1, 0.06)
		);

		const leg = MeshBuilder.CreateCylinder(
			`${asset.id}-body`,
			{
				diameterTop,
				diameterBottom,
				height,
				tessellation: 40
			},
			sceneRef
		);

		leg.parent = root;
		leg.position.y = -height / 2;
		leg.material = wood;

		registerObject({
			id: asset.id,
			type: 'leg',
			label: asset.label,
			root,
			meshes: [leg],
			mountPoints: {
				top: new Vector3(0, 0, 0)
			},
			graspPoint: new Vector3(0, 0, 0)
		});
	}

	function createDowel(asset: AssetInstance, sceneRef: Scene) {
		const root = new TransformNode(asset.id, sceneRef);
		root.position = v3(asset.position);
		root.rotation = v3(asset.rotation);

		const length = optionNumber(asset.options, 'length', 0.76);
		const diameter = optionNumber(asset.options, 'diameter', 0.16);

		const wood = createMaterial(
			`${asset.id}-wood-material`,
			new Color3(0.78, 0.55, 0.31),
			new Color3(0.18, 0.12, 0.08)
		);

		const dowel = MeshBuilder.CreateCylinder(
			`${asset.id}-body`,
			{
				diameter,
				height: length,
				tessellation: 40
			},
			sceneRef
		);

		dowel.parent = root;
		dowel.material = wood;

		registerObject({
			id: asset.id,
			type: 'dowel',
			label: asset.label,
			root,
			meshes: [dowel],
			mountPoints: {},
			graspPoint: new Vector3(0, 0.2, 0)
		});
	}

	function createScrew(asset: AssetInstance, sceneRef: Scene) {
		const root = new TransformNode(asset.id, sceneRef);
		root.position = v3(asset.position);
		root.rotation = v3(asset.rotation);

		const metal = createMaterial(
			`${asset.id}-metal-material`,
			new Color3(0.72, 0.74, 0.78),
			new Color3(0.65, 0.65, 0.7)
		);

		const dark = createMaterial(
			`${asset.id}-slot-material`,
			new Color3(0.04, 0.04, 0.045),
			new Color3(0.02, 0.02, 0.025)
		);

		const headDiameter = optionNumber(asset.options, 'headDiameter', 0.22);
		const headHeight = optionNumber(asset.options, 'headHeight', 0.12);
		const shaftDiameter = optionNumber(asset.options, 'shaftDiameter', 0.075);
		const shaftLength = optionNumber(asset.options, 'shaftLength', 0.62);
		const tipHeight = optionNumber(asset.options, 'tipHeight', 0.18);

		const head = MeshBuilder.CreateCylinder(
			`${asset.id}-head`,
			{
				diameter: headDiameter,
				height: headHeight,
				tessellation: 48
			},
			sceneRef
		);
		head.parent = root;
		head.position.y = 0.2;
		head.material = metal;

		const shaft = MeshBuilder.CreateCylinder(
			`${asset.id}-shaft`,
			{
				diameter: shaftDiameter,
				height: shaftLength,
				tessellation: 36
			},
			sceneRef
		);
		shaft.parent = root;
		shaft.position.y = -0.17;
		shaft.material = metal;

		const tip = MeshBuilder.CreateCylinder(
			`${asset.id}-tip`,
			{
				diameterTop: shaftDiameter,
				diameterBottom: 0,
				height: tipHeight,
				tessellation: 36
			},
			sceneRef
		);
		tip.parent = root;
		tip.position.y = -0.57;
		tip.material = metal;

		const slot = MeshBuilder.CreateBox(
			`${asset.id}-slot`,
			{
				width: headDiameter * 0.78,
				height: 0.018,
				depth: 0.036
			},
			sceneRef
		);
		slot.parent = root;
		slot.position.y = 0.265;
		slot.material = dark;

		registerObject({
			id: asset.id,
			type: 'screw',
			label: asset.label,
			root,
			meshes: [head, shaft, tip, slot],
			mountPoints: {},
			graspPoint: new Vector3(0, 0.23, 0)
		});
	}

	function createTool(asset: AssetInstance, sceneRef: Scene) {
		const root = new TransformNode(asset.id, sceneRef);
		root.position = v3(asset.position);
		root.rotation = v3(asset.rotation);

		const width = optionNumber(asset.options, 'width', 0.34);
		const height = optionNumber(asset.options, 'height', 0.22);
		const depth = optionNumber(asset.options, 'depth', 0.82);

		const material = createMaterial(
			`${asset.id}-tool-material`,
			new Color3(0.26, 0.34, 0.48),
			new Color3(0.22, 0.22, 0.28)
		);

		const handleMaterial = createMaterial(
			`${asset.id}-handle-material`,
			new Color3(0.08, 0.1, 0.14),
			new Color3(0.08, 0.08, 0.1)
		);

		const body = MeshBuilder.CreateBox(
			`${asset.id}-body`,
			{
				width,
				height,
				depth
			},
			sceneRef
		);
		body.parent = root;
		body.material = material;

		const handle = MeshBuilder.CreateCylinder(
			`${asset.id}-handle`,
			{
				diameter: width * 0.45,
				height: depth * 0.75,
				tessellation: 32
			},
			sceneRef
		);
		handle.parent = root;
		handle.rotation.x = Math.PI / 2;
		handle.position.y = height * 0.75;
		handle.material = handleMaterial;

		registerObject({
			id: asset.id,
			type: 'tool',
			label: asset.label,
			root,
			meshes: [body, handle],
			mountPoints: {},
			graspPoint: new Vector3(0, 0.28, 0)
		});
	}

	function createGripper(sceneRef: Scene) {
		gripperRoot = new TransformNode('robot-gripper-root', sceneRef);
		gripperRoot.position = new Vector3(-4.25, 2.25, 0);
		dynamicRoots.push(gripperRoot);

		const material = createMaterial(
			'gripper-material',
			new Color3(0.76, 0.82, 0.92),
			new Color3(0.35, 0.35, 0.4)
		);

		const palm = MeshBuilder.CreateBox(
			'robot-gripper-palm',
			{
				width: 0.46,
				height: 0.16,
				depth: 0.22
			},
			sceneRef
		);
		palm.parent = gripperRoot;
		palm.position.y = 0.18;
		palm.material = material;
		makeEdges(palm);
		addShadow(palm);

		gripperLeft = MeshBuilder.CreateBox(
			'robot-gripper-left',
			{
				width: 0.08,
				height: 0.46,
				depth: 0.08
			},
			sceneRef
		);
		gripperLeft.parent = gripperRoot;
		gripperLeft.position = new Vector3(0, -0.08, -0.25);
		gripperLeft.material = material;
		makeEdges(gripperLeft);
		addShadow(gripperLeft);

		gripperRight = MeshBuilder.CreateBox(
			'robot-gripper-right',
			{
				width: 0.08,
				height: 0.46,
				depth: 0.08
			},
			sceneRef
		);
		gripperRight.parent = gripperRoot;
		gripperRight.position = new Vector3(0, -0.08, 0.25);
		gripperRight.material = material;
		makeEdges(gripperRight);
		addShadow(gripperRight);
	}

	function createAsset(asset: AssetInstance, sceneRef: Scene) {
		if (asset.type === 'panel') createPanel(asset, sceneRef);
		if (asset.type === 'leg') createLeg(asset, sceneRef);
		if (asset.type === 'dowel') createDowel(asset, sceneRef);
		if (asset.type === 'screw') createScrew(asset, sceneRef);
		if (asset.type === 'tool') createTool(asset, sceneRef);
	}

	function buildSceneFromProgram(program: ParsedAssemblyProgram) {
		if (!scene) return;

		clearDynamicScene();

		const model = buildModelFromAspProgram(program);

		currentProgram = program;
		currentModel = model;
		commands = model.commands;
		parsedCommands = model.commands;
		parsedSteps = program.steps;
		parsedRepetitions = program.repetitions;

		for (const asset of model.assets) {
			createAsset(asset, scene);
		}

		createGripper(scene);
		resetScene();
	}

	function buildSceneFromModel(model: FurnitureModel) {
		if (!scene) return;

		clearDynamicScene();

		currentModel = model;
		commands = model.commands;
		parsedCommands = model.commands;

		for (const asset of model.assets) {
			createAsset(asset, scene);
		}

		createGripper(scene);
		resetScene();
	}

	function looksLikeAspProgram(value: string) {
		return /(?:^|\n)\s*(step|repetition|robot_command)\s*\(/.test(value);
	}

	function pickStringField(payload: unknown, keys: string[]) {
		if (!payload || typeof payload !== 'object') return '';

		const record = payload as Record<string, unknown>;

		for (const key of keys) {
			const value = record[key];

			if (typeof value === 'string' && value.trim().length > 0) {
				return value.trim();
			}

			if (typeof value === 'number') {
				return String(value);
			}
		}

		return '';
	}

	function findAspTextInJson(payload: unknown): string {
		if (typeof payload === 'string') {
			return looksLikeAspProgram(payload) ? payload : '';
		}

		if (Array.isArray(payload)) {
			for (const item of payload) {
				const found = findAspTextInJson(item);
				if (found) return found;
			}

			return '';
		}

		if (!payload || typeof payload !== 'object') return '';

		const record = payload as Record<string, unknown>;
		const preferredKeys = [
			'asp',
			'asp_program',
			'program',
			'input',
			'content',
			'text',
			'result',
			'output',
			'page_content',
			'commands'
		];

		for (const key of preferredKeys) {
			const value = record[key];

			if (typeof value === 'string' && looksLikeAspProgram(value)) {
				return value;
			}
		}

		for (const value of Object.values(record)) {
			const found = findAspTextInJson(value);
			if (found) return found;
		}

		return '';
	}

	async function readApiResponse(response: Response) {
		const raw = await response.text();
		const trimmed = raw.trim();

		let parsedErrorPayload: unknown = null;

		if (!response.ok) {
			try {
				parsedErrorPayload = trimmed ? JSON.parse(trimmed) : null;
			} catch {
				parsedErrorPayload = null;
			}

			const errorMessage =
				pickStringField(parsedErrorPayload, ['error', 'detail', 'message']) ||
				trimmed ||
				`Errore HTTP ${response.status}`;

			throw new Error(errorMessage);
		}

		let payload: unknown = trimmed;
		const contentType = response.headers.get('content-type') ?? '';

		if (contentType.includes('application/json') || trimmed.startsWith('{') || trimmed.startsWith('[')) {
			try {
				payload = JSON.parse(trimmed);
			} catch {
				payload = trimmed;
			}
		}

		if (typeof payload === 'string') {
			return {
				aspText: payload,
				sessionId: '',
				pageId: '',
				status: '',
				message: '',
				totalPages: ''
			};
		}

		const sessionFromPayload =
			pickStringField(payload, [
				'session_id',
				'sessionId',
				'session',
				'pdf_session_id',
				'pdfSessionId'
			]) || sessionId;

		const pageFromPayload =
			pickStringField(payload, ['page_id', 'pageId', 'current_page_id', 'currentPageId']) || pageId;

		return {
			aspText: findAspTextInJson(payload),
			sessionId: sessionFromPayload,
			pageId: pageFromPayload,
			status: pickStringField(payload, ['status']),
			message: pickStringField(payload, ['message']),
			totalPages: pickStringField(payload, ['total_pages', 'totalPages'])
		};
	}

	function applyAspProgramFromApi(aspText: string, sourceLabel: string) {
		const normalizedAspText = aspText.trim();

		if (!normalizedAspText) {
			throw new Error('La risposta della API non contiene un programma ASP-like valido.');
		}

		const parsed = parseAssemblyProgram(normalizedAspText);

		aspInput = normalizedAspText;
		parseError = '';
		apiError = '';
		buildSceneFromProgram(parsed);
		statusText = sourceLabel;
	}

	function handlePdfFileChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0] ?? null;

		selectedPdfFile = file;
		uploadedPdfName = file?.name ?? '';
		apiError = '';

		if (file) {
			apiStatusText = `Selected PDF: ${file.name}`;
		} else {
			apiStatusText = 'Upload a furniture assembly manual PDF to generate the 3D sequence.';
		}
	}

	async function fetchPageProgram(cleanSessionId: string, cleanPageId: string) {
		const response = await fetch(
			`${API_BASE_URL}/get_page/${encodeURIComponent(cleanSessionId)}/${encodeURIComponent(cleanPageId)}`
		);
		const result = await readApiResponse(response);

		if (result.sessionId) sessionId = result.sessionId;
		if (result.pageId) pageId = result.pageId;

		if (result.status === 'completed') {
			apiStatusText = result.message || 'Tutte le pagine sono state elaborate.';
			return;
		}

		applyAspProgramFromApi(result.aspText, `Loaded page ${pageId} from API`);
		apiStatusText = `Loaded page ${pageId}.`;
	}

	async function loadPageFromApi() {
		if (isPlaying || isUploadingPdf || isLoadingPage) return;

		const cleanSessionId = sessionId.trim();
		const cleanPageId = pageId.trim();

		if (!cleanSessionId) {
			apiError = 'Session ID mancante. Carica prima un PDF o inserisci una sessione valida.';
			return;
		}

		if (!cleanPageId) {
			apiError = 'Page ID mancante.';
			return;
		}

		isLoadingPage = true;
		apiError = '';
		apiStatusText = `Loading page ${cleanPageId} for session ${cleanSessionId}...`;

		try {
			await fetchPageProgram(cleanSessionId, cleanPageId);
		} catch (error) {
			apiError = error instanceof Error ? error.message : 'Errore durante il caricamento della pagina.';
		} finally {
			isLoadingPage = false;
		}
	}

	async function uploadPdf() {
		if (isPlaying || isUploadingPdf || isLoadingPage) return;

		if (!selectedPdfFile) {
			apiError = 'Seleziona un PDF prima di avviare upload.';
			return;
		}

		isUploadingPdf = true;
		apiError = '';
		apiStatusText = `Uploading ${selectedPdfFile.name}...`;

		try {
			const formData = new FormData();
			formData.append('pdf', selectedPdfFile);

			const response = await fetch(`${API_BASE_URL}/upload_pdf`, {
				method: 'POST',
				body: formData
			});

			const result = await readApiResponse(response);

			if (result.sessionId) sessionId = result.sessionId;
			pageId = result.pageId || DEFAULT_PAGE_ID;

			if (result.aspText) {
				applyAspProgramFromApi(result.aspText, 'Loaded sequence from uploaded PDF');
				apiStatusText = result.sessionId
					? `PDF uploaded. Session ${sessionId}. Sequence loaded.`
					: 'PDF uploaded. Sequence loaded.';
			} else if (sessionId) {
				const totalPagesLabel = result.totalPages ? ` Total pages: ${result.totalPages}.` : '';
				apiStatusText = `PDF uploaded. Session ${sessionId}.${totalPagesLabel} Loading page ${pageId}...`;
				await fetchPageProgram(sessionId.trim(), pageId.trim());
			} else {
				throw new Error(
					'Upload completato, ma la risposta non contiene né programma ASP-like né session_id.'
				);
			}
		} catch (error) {
			apiError = error instanceof Error ? error.message : 'Errore durante upload del PDF.';
		} finally {
			isUploadingPdf = false;
		}
	}

	function applyAspInput() {
		if (isPlaying) return;

		try {
			const parsed = parseAssemblyProgram(aspInput);

			parseError = '';
			buildSceneFromProgram(parsed);
		} catch (error) {
			parseError = error instanceof Error ? error.message : 'Input non valido.';
		}
	}

	function restoreDefaultAsp() {
		if (isPlaying) return;

		aspInput = DEFAULT_ASP_INPUT;
		parseError = '';

		const parsed = parseAssemblyProgram(DEFAULT_ASP_INPUT);

		buildSceneFromProgram(parsed);
	}

	onMount(() => {
		engine = new Engine(canvas, true, {
			preserveDrawingBuffer: true,
			stencil: true,
			antialias: true
		});

		scene = new Scene(engine);
		scene.clearColor = new Color4(0.02, 0.03, 0.07, 1);

		const camera = new ArcRotateCamera(
			'main-camera',
			Math.PI / 4,
			Math.PI / 3.05,
			6.9,
			new Vector3(0, 0.85, 0),
			scene
		);

		camera.attachControl(canvas, true);
		camera.lowerRadiusLimit = 3;
		camera.upperRadiusLimit = 13;
		camera.wheelDeltaPercentage = 0.01;

		const hemiLight = new HemisphericLight('hemi-light', new Vector3(0, 1, 0), scene);
		hemiLight.intensity = 0.58;

		const dirLight = new DirectionalLight('dir-light', new Vector3(-1.1, -2.2, -1), scene);
		dirLight.position = new Vector3(4.5, 7, 5);
		dirLight.intensity = 1.15;

		shadowGenerator = new ShadowGenerator(2048, dirLight);
		shadowGenerator.useBlurExponentialShadowMap = true;
		shadowGenerator.blurKernel = 32;
		shadowGenerator.darkness = 0.35;

		const groundMaterial = createMaterial(
			'ground-material',
			new Color3(0.1, 0.13, 0.22),
			new Color3(0.04, 0.04, 0.08)
		);

		const ground = MeshBuilder.CreateGround(
			'ground',
			{
				width: 10,
				height: 10,
				subdivisions: 12
			},
			scene
		);
		ground.material = groundMaterial;
		ground.receiveShadows = true;

		buildSceneFromProgram(DEFAULT_PROGRAM);

		engine.runRenderLoop(() => {
			scene?.render();
		});

		const handleResize = () => {
			engine?.resize();
		};

		window.addEventListener('resize', handleResize);

		return () => {
			window.removeEventListener('resize', handleResize);

			scene?.dispose();
			engine?.dispose();
		};
	});
</script>

<svelte:head>
	<title>Furniture Assembly 3D PoC</title>
</svelte:head>

<main class="page">
	<section class="sidebar">
		<p class="eyebrow">Furniture Assembly PoC</p>

		<h1>Manual-grounded 3D Viewer</h1>

		<p class="description">
			Viewer Babylon.js con workflow REST: upload del manuale PDF, recupero della pagina
			elaborata e visualizzazione 3D dei fatti ASP-like generati dalla pipeline.
		</p>


		<div class="api-panel">
			<div class="section-title-row">
				<h2>PDF workflow</h2>
			</div>

			<label class="file-picker">
				<span>Select manual PDF</span>
				<input type="file" accept="application/pdf,.pdf" onchange={handlePdfFileChange} disabled={isPlaying || isUploadingPdf || isLoadingPage} />
			</label>

			{#if uploadedPdfName}
				<p class="file-name">{uploadedPdfName}</p>
			{/if}

			<div class="api-actions">
				<button type="button" onclick={uploadPdf} disabled={isPlaying || isUploadingPdf || isLoadingPage || !selectedPdfFile}>
					{isUploadingPdf ? 'Uploading...' : 'Upload PDF'}
				</button>
			</div>

			<div class="api-grid">
				<label>
					<span>Session ID</span>
					<input bind:value={sessionId} placeholder="session_id" disabled={isPlaying || isUploadingPdf || isLoadingPage} />
				</label>

				<label>
					<span>Page ID</span>
					<input bind:value={pageId} placeholder="page_id" disabled={isPlaying || isUploadingPdf || isLoadingPage} />
				</label>
			</div>

			<button type="button" class="secondary full" onclick={loadPageFromApi} disabled={isPlaying || isUploadingPdf || isLoadingPage || !sessionId || !pageId}>
				{isLoadingPage ? 'Loading page...' : 'Load page from API'}
			</button>

			<p class="api-status">{apiStatusText}</p>

			{#if apiError}
				<p class="error">{apiError}</p>
			{/if}
		</div>

		<div class="controls">
			<button type="button" onclick={playAll} disabled={isPlaying || isUploadingPdf || isLoadingPage}>
				Play sequence
			</button>

			<button type="button" class="secondary" onclick={resetScene} disabled={isPlaying || isUploadingPdf || isLoadingPage}>
				Reset
			</button>
		</div>

		<div class="status">
			<p>{statusText}</p>
		</div>

		<div class="legend">
			<h2>Asset vocabulary</h2>

			<div class="asset-grid">
				<span>screw</span>
				<span>dowel</span>
				<span>panel</span>
				<span>tool</span>
			</div>
		</div>

		<div class="json-editor">
			<div class="section-title-row">
				<h2>Current ASP-like input</h2>

				<div class="json-actions">
					<button type="button" class="small secondary" onclick={restoreDefaultAsp} disabled={isPlaying || isUploadingPdf || isLoadingPage}>
						Default
					</button>

					<button type="button" class="small" onclick={applyAspInput} disabled={isPlaying || isUploadingPdf || isLoadingPage}>
						Apply input
					</button>
				</div>
			</div>

			<textarea bind:value={aspInput} spellcheck="false"></textarea>

			{#if parseError}
				<p class="error">{parseError}</p>
			{/if}
		</div>

		<div class="commands">
			<h2>Assembly commands</h2>

			{#each commands as command, index}
				<button
					type="button"
					class:active={currentCommandIndex === index}
					class="command-card"
					onclick={() => playSingle(index)}
					disabled={isPlaying || isUploadingPdf || isLoadingPage}
				>
					<span class="command-top">
						<span>Step {command.step}</span>
						<span>{command.order}. {command.command}</span>
					</span>

					{#if command.repetitionCount && command.repetitionCount > 1}
						<span class="repetition-badge">
							Repetition {command.repetitionIndex}/{command.repetitionCount} · {command.objectId}
						</span>
					{/if}

					<span class="command-description">
						{command.description}
					</span>
				</button>
			{/each}
		</div>

		<details class="debug">
			<summary>Parsed program</summary>
			<pre>{JSON.stringify({ steps: parsedSteps, repetitions: parsedRepetitions }, null, 2)}</pre>
		</details>

		<details class="debug">
			<summary>Parsed commands</summary>
			<pre>{JSON.stringify(parsedCommands, null, 2)}</pre>
		</details>

		<details class="debug">
			<summary>Generated visual model</summary>
			<pre>{JSON.stringify(currentModel, null, 2)}</pre>
		</details>
	</section>

	<section class="viewer">
		<canvas bind:this={canvas}></canvas>

		<div class="viewer-label">
			<div>
				<strong>{currentModel.title}</strong>
				<span>{currentModel.description}</span>
			</div>

			<div>
				<strong>current task</strong>
				<span>{commands.length} executable commands</span>
			</div>
		</div>
	</section>
</main>

<style>
	:global(body) {
		margin: 0;
		font-family:
			Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
			sans-serif;
		background: #0f172a;
		color: #e5e7eb;
	}

	:global(*) {
		box-sizing: border-box;
	}

	.page {
		min-height: 100vh;
		display: grid;
		grid-template-columns: 500px 1fr;
	}

	.sidebar {
		height: 100vh;
		overflow: auto;
		padding: 28px;
		background: #111827;
		border-right: 1px solid rgba(255, 255, 255, 0.08);
	}

	.eyebrow {
		margin: 0 0 12px;
		color: #93c5fd;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		font-size: 0.75rem;
		font-weight: 800;
	}

	h1 {
		margin: 0;
		font-size: 1.9rem;
		line-height: 1.1;
	}

	.description {
		margin-top: 16px;
		color: #cbd5e1;
		line-height: 1.6;
	}

	.api-panel {
		margin-top: 22px;
		padding: 14px;
		border-radius: 16px;
		background: rgba(255, 255, 255, 0.05);
		border: 1px solid rgba(255, 255, 255, 0.08);
	}

	.file-picker {
		display: grid;
		gap: 8px;
		padding: 12px;
		border-radius: 14px;
		background: rgba(2, 6, 23, 0.45);
		border: 1px dashed rgba(147, 197, 253, 0.32);
		color: #bfdbfe;
		font-size: 0.84rem;
		font-weight: 900;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.file-picker input {
		width: 100%;
		color: #cbd5e1;
		font-size: 0.84rem;
		text-transform: none;
		letter-spacing: normal;
		font-weight: 700;
	}

	.file-name {
		margin: 10px 0 0;
		color: #dbeafe;
		font-size: 0.86rem;
		line-height: 1.4;
		word-break: break-word;
	}

	.api-actions {
		display: grid;
		margin-top: 12px;
	}

	.api-grid {
		display: grid;
		grid-template-columns: 1fr 0.6fr;
		gap: 10px;
		margin-top: 12px;
	}

	.api-grid label {
		display: grid;
		gap: 6px;
		color: #cbd5e1;
		font-size: 0.78rem;
		font-weight: 900;
		letter-spacing: 0.06em;
		text-transform: uppercase;
	}

	.api-grid input {
		width: 100%;
		border: 1px solid rgba(148, 163, 184, 0.25);
		border-radius: 12px;
		padding: 10px 11px;
		background: rgba(2, 6, 23, 0.78);
		color: #dbeafe;
		font-size: 0.86rem;
		outline: none;
	}

	.api-grid input:focus {
		border-color: rgba(129, 140, 248, 0.8);
		box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.18);
	}

	button.full {
		width: 100%;
		margin-top: 12px;
	}

	.api-status {
		margin: 12px 0 0;
		padding: 10px 12px;
		border-radius: 12px;
		background: rgba(15, 23, 42, 0.7);
		border: 1px solid rgba(255, 255, 255, 0.08);
		color: #cbd5e1;
		font-size: 0.84rem;
		line-height: 1.45;
	}

	.json-editor {
		margin-top: 22px;
		padding: 14px;
		border-radius: 16px;
		background: rgba(255, 255, 255, 0.05);
		border: 1px solid rgba(255, 255, 255, 0.08);
	}

	.controls {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
		margin-top: 24px;
	}

	button {
		border: 0;
		border-radius: 12px;
		padding: 12px 16px;
		background: #4f46e5;
		color: white;
		font-weight: 800;
		cursor: pointer;
	}

	button:hover:not(:disabled) {
		background: #4338ca;
	}

	button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	button.secondary {
		background: #334155;
	}

	button.secondary:hover:not(:disabled) {
		background: #475569;
	}

	button.small {
		padding: 8px 10px;
		border-radius: 10px;
		font-size: 0.78rem;
	}

	.status {
		margin-top: 16px;
		padding: 14px;
		border-radius: 14px;
		background: rgba(15, 23, 42, 0.85);
		border: 1px solid rgba(255, 255, 255, 0.08);
		color: #cbd5e1;
		font-size: 0.92rem;
		line-height: 1.5;
	}

	.status p {
		margin: 0;
	}

	.legend {
		margin-top: 22px;
	}

	.legend h2,
	.commands h2,
	.json-editor h2 {
		margin: 0 0 12px;
		font-size: 1rem;
		color: #e2e8f0;
	}

	.asset-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 10px;
	}

	.asset-grid span {
		padding: 10px 12px;
		border-radius: 12px;
		background: rgba(147, 197, 253, 0.09);
		border: 1px solid rgba(147, 197, 253, 0.18);
		color: #bfdbfe;
		font-size: 0.85rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.section-title-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		margin-bottom: 10px;
	}

	.section-title-row h2 {
		margin: 0;
	}

	.json-actions {
		display: flex;
		gap: 8px;
	}

	textarea {
		width: 100%;
		min-height: 280px;
		resize: vertical;
		border: 1px solid rgba(148, 163, 184, 0.25);
		border-radius: 14px;
		padding: 12px;
		background: rgba(2, 6, 23, 0.78);
		color: #dbeafe;
		font-family:
			"JetBrains Mono", "Fira Code", Consolas, "Liberation Mono", monospace;
		font-size: 0.76rem;
		line-height: 1.45;
		outline: none;
	}

	textarea:focus {
		border-color: rgba(129, 140, 248, 0.8);
		box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.18);
	}

	.error {
		margin: 10px 0 0;
		padding: 10px 12px;
		border-radius: 12px;
		background: rgba(239, 68, 68, 0.12);
		border: 1px solid rgba(248, 113, 113, 0.35);
		color: #fecaca;
		font-size: 0.86rem;
		line-height: 1.45;
	}

	.commands {
		margin-top: 24px;
	}

	.command-card {
		width: 100%;
		display: block;
		margin-bottom: 12px;
		padding: 14px;
		text-align: left;
		border-radius: 14px;
		background: rgba(255, 255, 255, 0.06);
		border: 1px solid rgba(255, 255, 255, 0.08);
		color: #e5e7eb;
	}

	.command-card:hover:not(:disabled),
	.command-card.active {
		background: rgba(79, 70, 229, 0.25);
		border-color: rgba(129, 140, 248, 0.6);
	}

	.command-top {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		margin-bottom: 8px;
		color: #93c5fd;
		font-size: 0.76rem;
		font-weight: 900;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.repetition-badge {
		display: inline-block;
		margin-bottom: 8px;
		padding: 5px 8px;
		border-radius: 999px;
		background: rgba(34, 197, 94, 0.13);
		border: 1px solid rgba(74, 222, 128, 0.32);
		color: #bbf7d0;
		font-size: 0.74rem;
		font-weight: 900;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.command-description {
		display: block;
		color: #cbd5e1;
		font-size: 0.92rem;
		line-height: 1.45;
	}

	.debug {
		margin-top: 16px;
		border-radius: 14px;
		background: rgba(255, 255, 255, 0.05);
		border: 1px solid rgba(255, 255, 255, 0.08);
		overflow: hidden;
	}

	.debug summary {
		padding: 12px 14px;
		cursor: pointer;
		font-weight: 800;
		color: #e2e8f0;
	}

	pre {
		margin: 0;
		padding: 14px;
		overflow: auto;
		max-height: 340px;
		background: rgba(2, 6, 23, 0.75);
		color: #cbd5e1;
		font-size: 0.76rem;
		line-height: 1.45;
	}

	.viewer {
		position: relative;
		min-height: 100vh;
		background:
			radial-gradient(circle at top, rgba(79, 70, 229, 0.25), transparent 35%),
			#020617;
	}

	canvas {
		display: block;
		width: 100%;
		height: 100%;
		outline: none;
		touch-action: none;
	}

	.viewer-label {
		position: absolute;
		left: 24px;
		right: 24px;
		bottom: 24px;
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		pointer-events: none;
	}

	.viewer-label div {
		max-width: 520px;
		padding: 12px 14px;
		border-radius: 14px;
		background: rgba(15, 23, 42, 0.82);
		border: 1px solid rgba(255, 255, 255, 0.1);
		backdrop-filter: blur(10px);
	}

	.viewer-label strong {
		display: block;
		color: #e5e7eb;
	}

	.viewer-label span {
		display: block;
		margin-top: 4px;
		color: #cbd5e1;
		font-size: 0.88rem;
		line-height: 1.4;
	}

	@media (max-width: 1100px) {
		.page {
			grid-template-columns: 1fr;
		}

		.sidebar {
			height: auto;
			border-right: 0;
			border-bottom: 1px solid rgba(255, 255, 255, 0.08);
		}

		.viewer {
			min-height: 72vh;
		}
	}
</style>