/**
 * Образец НЕподдерживаемой конструкции: условный тип внутри достижимого графа.
 * Экстрактор обязан упасть (fail-closed) с указанием файла и строки.
 */

export interface Bad {
  value: string extends unknown ? never : string;
}
