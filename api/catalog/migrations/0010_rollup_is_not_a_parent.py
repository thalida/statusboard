from django.db import migrations

# `is_overall` belongs to the parent row, not the row being written. A
# `CheckConstraint` sees one row, so it cannot read a joined column and
# cannot express "my parent is not the rollup". A trigger can, because
# it runs a query rather than evaluating an expression.
#
# The function checks both directions of the same rule. A row cannot be
# inserted or reparented under the rollup. A row cannot gain the rollup
# flag while something already points at it as a parent. Either gap
# would corrupt every descendant count and breadcrumb under it.
CREATE_TRIGGER = """
CREATE FUNCTION catalog_component_rollup_is_not_a_parent()
RETURNS trigger AS $$
BEGIN
    IF NEW.parent_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM catalog_servicecomponent
        WHERE id = NEW.parent_id AND is_overall
    ) THEN
        RAISE EXCEPTION
            'rollup_is_not_a_parent: % cannot be parented under the overall component',
            NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.is_overall AND EXISTS (
        SELECT 1 FROM catalog_servicecomponent WHERE parent_id = NEW.id
    ) THEN
        RAISE EXCEPTION
            'rollup_is_not_a_parent: % already has children, so it cannot become the overall component',
            NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER rollup_is_not_a_parent
    BEFORE INSERT OR UPDATE OF parent_id, is_overall ON catalog_servicecomponent
    FOR EACH ROW
    EXECUTE FUNCTION catalog_component_rollup_is_not_a_parent();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS rollup_is_not_a_parent ON catalog_servicecomponent;
DROP FUNCTION IF EXISTS catalog_component_rollup_is_not_a_parent();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_history_drops_search_document"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
